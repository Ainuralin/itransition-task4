# Bookstore Analytics

**Ainur Ali · Itransition Data Engineering · Task 4**

This is my solution for the bookstore data analysis task. I used pandas to clean the data from five stores and Flask to serve a dashboard with three views: Overview, Customers and Authors.

The chat uses Groq to answer questions about the data. Calculations run in Python through function calls, and the model uses the returned results to write its answer.

## Dashboard

Each store has its own results:

- Top five days by revenue and a daily revenue chart.
- Number of unique customers after matching their profiles.
- Number of distinct author sets in the catalog.
- Most popular author set by the number of books sold.
- Customer with the highest total spending, including all associated user IDs.

The Customers and Authors views show rankings. The daily revenue data can also be exported as CSV. The chart range selector affects only the chart; the summary cards and rankings cover the whole dataset.

## Data processing

The input archive is `data/data.zip`. Each store contains `users.csv`, `orders.parquet` and `books.yaml`. Stores are processed separately.

### Prices and dates

Prices use several formats, including `USD25.25`, `$35¢25` and `EUR37.50`. I convert EUR to USD at the rate **€1 = $1.20**. Converted unit prices are rounded to cents before multiplying by quantity. Revenue is summed in integer cents to avoid floating-point rounding errors.

Timestamps also use different formats. Slash dates are read as `MM/DD/YY`, dotted dates as `DD.MM.YYYY`, and named months are parsed separately. Invalid dates stay missing rather than being replaced with the current date. The original timestamp is kept in the cleaned orders table.

### Customer matching

I compare four fields: name, address, phone and email. Text is normalized for case and whitespace, and punctuation is removed from phone numbers. Profiles are linked when at least three nonmissing fields match. This follows the task's assumption that any one field can change.

Linked profiles form one customer. The smallest user ID identifies the group, while the full list of IDs is kept for reporting. Spending is calculated across all profiles in that group. The matching links are saved in `reconciliation_links.csv` so the groups can be inspected.

### Authors and missing values

Author names are split at commas, trimmed and sorted. Repeated names within a set are removed. This makes `John, Paul` and `Paul, John` the same set, while `John` remains a separate one. Unique author sets are counted across the full catalog. Popularity is based on the sum of quantities sold.

Blank values and text markers such as `NULL` are treated as missing. Missing addresses and shipping details are kept. Invalid publication years are set to missing. Orders with invalid prices, dates, quantities or references are saved in `rejected_orders.csv`. Exact duplicate rows are removed; conflicting duplicate IDs stop processing.

## Results

| Store  | Orders | Unique customers | Author sets | Revenue (USD) |
| ------ | -----: | ---------------: | ----------: | ------------: |
| STORE1 | 10,493 |            3,221 |         324 |    739,354.03 |
| STORE2 |  9,181 |            3,166 |         281 |    668,103.84 |
| STORE3 |  9,280 |            2,955 |         307 |    681,626.00 |
| STORE4 | 10,877 |            2,850 |         299 |    778,289.82 |
| STORE5 |  9,714 |            2,987 |         311 |    704,422.31 |

All 49,545 orders in the supplied dataset passed validation. Full results and cleaned tables are saved under `output/STORE1` through `output/STORE5`.

## Running locally

Python 3.11 or 3.12 is recommended. In Windows CMD:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python analyze.py
python app.py
```

The dashboard runs at http://127.0.0.1:5000.

For chat, set `GROQ_API_KEY` in the server environment or start with:

```cmd
python start_chat.py
```

The startup script asks for the key without displaying it and keeps it in memory for the session. The default model is `openai/gpt-oss-120b`, hosted by Groq. `GROQ_MODEL` can override it. The `.env.example` file lists these variables; `.env` files are not loaded automatically.

## Chat

The assistant has six tools:

| Tool               | Purpose                                                        |
| ------------------ | -------------------------------------------------------------- |
| `store_summary`    | Store totals, top days, best buyer and popular author sets     |
| `revenue_between`  | Revenue, orders and books sold over a date range               |
| `customer_details` | Customer profiles and spending, searched by ID or email        |
| `author_sales`     | Author-set rankings, with an optional individual author filter |
| `search_books`     | Search the catalog by title or author                          |
| `show_view`        | Select a store and switch dashboard views                      |

Questions are handled independently. Chat navigation supports store and view selection; other dashboard filters are controlled directly in the interface. Without a configured key, the dashboard still works and the chat is disabled.

Groq's Free tier has request and token limits. The application shows an error if a limit is reached. It does not switch to another provider.

## Tests

```cmd
python -m pytest -q
```

The tests cover price and date formats, customer matching, author sets, totals for all five stores, API routes and the chat tool loop. Provider responses are mocked in the automated chat tests. As a manual check, the STORE1 question about the top customer returns **$1,317.59** and IDs **[48403, 48904, 50056]**.

## Deployment

The Flask app can run on Render as a Python Web Service. The configuration is in `render.yaml`.

```text
Build: pip install -r requirements.txt && python analyze.py
Start: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120
```

Chat requires `GROQ_API_KEY` in the service's environment variables. The Free compute plan is used for the deployment configuration. A static deployment of `dist/` displays the dashboard but does not run the chat backend.

## Project files

```text
analyze.py          Load, clean and analyze the five stores
app.py              Flask routes and chat tools
start_chat.py       Local startup with a key prompt
test_analysis.py    Data processing tests
test_app.py         Backend and chat tests
data/data.zip       Original dataset
dist/               Dashboard HTML, CSS, JavaScript and summary data
output/             Cleaned tables and results for each store
requirements.txt    Python dependencies
render.yaml         Render service configuration
```

The frontend includes Marked and DOMPurify for rendering chat responses. Their licenses are in `dist/vendor/`.
