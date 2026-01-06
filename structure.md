TruePass_Blockchain/
├── app.py                # Routes & Logic
├── models.py             # DB Schema (User, Ticket, Transaction)
├── setup.py              # Run this once to create DB
├── static/
│   └── style.css         # CSS
└── templates/
    ├── base.html         # Main Layout
    ├── landing.html      # Home page (Not logged in)
    ├── login.html
    ├── register.html
    ├── dashboard.html    # Logged in view (Wallet)
    └── market_view.html  # Public reseller page