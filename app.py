import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id=session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                      user_id=session["user_id"])[0]["cash"]

    total_value = cash
    grand_total = cash

    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["price"] = quote["price"]
        stock["value"] = quote["price"] * stock["total_shares"]
        total_value += stock["value"]
        grand_total += stock["value"]

    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("You must provide a symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("You must provide a positive integer of shares")

        quote = lookup(symbol)
        if quote is None:
            return apology("Symbol not found")

        price = quote["price"]
        total_cost = round(int(shares) * price, 2)
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=session["user_id"])[0]["cash"]
        if cash < total_cost:
            return apology("You don't have enough cash")

        db.execute("UPDATE users SET cash = cash - :total_cost WHERE id = :user_id",
                   total_cost=total_cost, user_id=session["user_id"])

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        flash(f"You bought {shares} shares of {symbol} for {usd(total_cost)}!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :user_id ORDER BY timestamp DESC",
                              user_id=session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("You must provide a symbol", 400)

        quote = lookup(symbol)
        if not quote:
            return apology("Invalid symbol", 400)

        # Si la solicitud es AJAX, devuelve una respuesta JSON
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(quote)

        return render_template("quote.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("You must provide a user name", 400)
        elif not request.form.get("password"):
            return apology("You must provide a password", 400)
        elif not request.form.get("confirmation"):
            return apology("You must confirm your password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Your passwords do NOT match", 400)
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(rows) != 0:
            return apology("This username already exists", 400)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                   request.form.get("username"), generate_password_hash(request.form.get("password")))
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        session["user_id"] = rows[0]["id"]
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                        user_id=session["user_id"])

    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("You must provide a symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("You must provide a positive integer number of shares")
        else:
            shares = int(shares)

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("You don't have enough shares")
                else:
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("Symbol not found")
                    price = quote["price"]
                    total_sale = shares * price

                    db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id",
                               total_sale=total_sale, user_id=session["user_id"])

                    db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                               user_id=session["user_id"], symbol=symbol, shares=-shares, price=price)

                    flash(f"You sold {shares} shares of {symbol} for {usd(total_sale)}")
                    return redirect("/")

        return apology("Symbol not found")
    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not current_password or not new_password or not confirm_password:
            return apology("All fields are required")

        user_id = session["user_id"]
        user = db.execute("SELECT * FROM users WHERE id = :user_id", user_id=user_id)

        if len(user) != 1 or not check_password_hash(user[0]["hash"], current_password):
            return apology("Current password is incorrect")

        if new_password != confirm_password:
            return apology("New passwords do not match")

        db.execute("UPDATE users SET hash = :new_hash WHERE id = :user_id",
                   new_hash=generate_password_hash(new_password), user_id=user_id)

        flash("Password changed successfully!")
        return redirect("/")

    else:
        return render_template("change_password.html")
