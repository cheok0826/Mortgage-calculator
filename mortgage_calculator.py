from flask import Flask, render_template_string, request
import math
import webbrowser
import threading
from tabulate import tabulate
import os
import signal

app = Flask(__name__)

# -----------------------
# Helper Functions (from your simulation)
# -----------------------

def calc_baseline_payment(principal, monthly_rate, n_months):
    return principal * monthly_rate * (1 + monthly_rate) ** n_months / ((1 + monthly_rate) ** n_months - 1)

def accelerated_term_analysis(principal, monthly_rate, original_term_years):
    n_original = original_term_years * 12
    baseline_payment = calc_baseline_payment(principal, monthly_rate, n_original)
    years = list(range(1, original_term_years + 1))
    summary_table = []
    for term in years:
        n_target = term * 12
        target_payment = principal * monthly_rate * (1 + monthly_rate) ** n_target / ((1 + monthly_rate) ** n_target - 1)
        extra_payment = target_payment - baseline_payment
        total_payment = target_payment * n_target
        total_interest = total_payment - principal
        remaining_baseline = principal * ((1 + monthly_rate) ** n_original - (1 + monthly_rate) ** n_target) / ((1 + monthly_rate) ** n_original - 1)
        advanced_principal = principal - remaining_baseline
        summary_table.append([
            term,
            f"RM{target_payment:,.2f}",
            f"RM{extra_payment:,.2f}",
            f"RM{total_interest:,.2f}",
            f"RM{advanced_principal:,.2f}"
        ])
    return baseline_payment, summary_table

def generate_amortization_schedule(principal, monthly_rate, n_months, monthly_payment):
    balance = principal
    schedule = []
    cumulative_principal = 0
    for month in range(1, n_months + 1):
        interest_payment = balance * monthly_rate
        principal_payment = monthly_payment - interest_payment
        cumulative_principal += principal_payment
        balance -= principal_payment
        if balance < 0:
            principal_payment += balance
            balance = 0
        schedule.append({
            'Month': month,
            'Payment': monthly_payment,
            'Interest': interest_payment,
            'Principal': principal_payment,
            'Cumulative Principal': cumulative_principal,
            'Remaining Balance': balance
        })
        if balance <= 0:
            break
    return schedule

def detailed_amortization(principal, monthly_rate, selected_term_years, baseline_payment):
    n_selected = selected_term_years * 12
    accelerated_payment = principal * monthly_rate * (1 + monthly_rate) ** n_selected / ((1 + monthly_rate) ** n_selected - 1)
    accelerated_schedule = generate_amortization_schedule(principal, monthly_rate, n_selected, accelerated_payment)
    baseline_schedule = generate_amortization_schedule(principal, monthly_rate, n_selected, baseline_payment)
    table = []
    cumulative_extra = 0
    for acc, base in zip(accelerated_schedule, baseline_schedule):
        extra_principal = acc['Principal'] - base['Principal']
        cumulative_extra += extra_principal
        table.append([
            acc['Month'],
            f"RM{acc['Payment']:,.2f}",
            f"RM{acc['Interest']:,.2f}",
            f"RM{acc['Principal']:,.2f}",
            f"RM{acc['Cumulative Principal']:,.2f}",
            f"RM{acc['Remaining Balance']:,.2f}",
            f"RM{extra_principal:,.2f}",
            f"RM{cumulative_extra:,.2f}"
        ])
    return accelerated_payment, table

def simulate_combined_offset_advance(principal, monthly_rate, fixed_payment, baseline_payment, offset_threshold, target_term_years):
    total_months = target_term_years * 12
    base_principal_paid = 0.0
    offset_total = 0.0
    extra_accumulated = 0.0
    schedule = []
    for m in range(1, total_months + 1):
        effective_outstanding = principal - (base_principal_paid + extra_accumulated + offset_total)
        interest_payment = effective_outstanding * monthly_rate
        accelerated_principal = fixed_payment - interest_payment

        baseline_balance = principal - base_principal_paid
        baseline_interest = baseline_balance * monthly_rate
        baseline_principal = baseline_payment - baseline_interest

        extra = accelerated_principal - baseline_principal
        if extra < 0:
            extra = 0
        extra_accumulated += extra
        base_principal_paid += baseline_principal

        offset_applied = 0
        if extra_accumulated >= offset_threshold:
            offset_applied = offset_threshold
            offset_total += offset_threshold
            extra_accumulated = 0  # reset extra

        total_effective_reduction = base_principal_paid + extra_accumulated + offset_total
        remaining_principal = principal - total_effective_reduction

        schedule.append({
            'Month': m,
            'Fixed Payment': fixed_payment,
            'Effective Outstanding': effective_outstanding,
            'Interest': interest_payment,
            'Accelerated Principal': accelerated_principal,
            'Baseline Principal': baseline_principal,
            'Extra Added': extra,
            'Extra Accumulated': extra_accumulated,
            'Offset Applied': offset_applied,
            'Baseline Paid': base_principal_paid,
            'Total Offset': offset_total,
            'Total Effective Reduction': total_effective_reduction,
            'Remaining Principal': remaining_principal
        })

        if remaining_principal <= 0:
            break

    return schedule

# -----------------------
# Flask Routes and Templates with Dark Theme and Left-Aligned Two-Column Layout
# -----------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mortgage Offset Simulation</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background-color: #121212; 
            color: #e0e0e0;
            text-align: left;
        }
        .container { 
            max-width: 100%; 
            margin: 2%; 
            text-align: left;
        }
        .row { 
            display: flex; 
            flex-wrap: wrap; 
            align-items: flex-start;
            margin-bottom: 20px; 
        }
        .column1 { 
            margin-right: 20px; 
            padding: 10px; 
        }
        .column2 { 
            flex: 55%; 
            padding: 10px; 
        }
        table { 
            border-collapse: collapse; 
            margin-bottom: 30px; 
            width: 100%;
        }
        th, td { 
            border: 1px solid #444; 
            padding: 8px; 
        }
        th { 
            background-color: #333; 
        }
        input { 
            padding: 5px; 
            margin: 5px 0; 
            background-color: #333; 
            color: #e0e0e0; 
            border: 1px solid #555; 
        }
        button { 
            padding: 8px 12px; 
            background-color: #555; 
            color: #e0e0e0; 
            border: none; 
            cursor: pointer; 
        }
        button:hover { 
            background-color: #666; 
        }
        label { 
            display: block; 
            margin-top: 10px; 
        }
    </style>
 <script>
        window.addEventListener("beforeunload", function () {
            navigator.sendBeacon('/shutdown');
        });
    </script>
</head>
<body>
<div class="container">
    <h1>Mortgage Offset Simulation</h1>
    <div class="row">
        <div class="column1">
            <form method="POST">
                <label>Principal (RM):</label>
                <input type="number" name="principal" step="any" value="{{ principal }}">
                <label>Annual Interest Rate (%):</label>
                <input type="number" name="annual_interest_rate" step="any" value="{{ annual_interest_rate }}">
                <label>Original Term (years):</label>
                <input type="number" name="original_term_years" value="{{ original_term_years }}">
                <label>Simulation Term (years):</label>
                <input type="number" name="simulation_term_years" value="{{ simulation_term_years }}">
                <label>Offset Threshold (RM):</label>
                <input type="number" name="offset_threshold" step="any" value="{{ offset_threshold }}">
                <br>
                <button type="submit">Simulate</button>
            </form>
        </div>
        <div class="column2">
            <h2>35-Year Accelerated Term Analysis Summary (Baseline)</h2>
            {{ baseline_summary|safe }}
        </div>
    </div>
    
    <h2>Detailed Amortization for Simulation Term (Default: {{ simulation_term_years }} years)</h2>
    <p>Derived Accelerated (Fixed) Payment: {{ accelerated_payment }}</p>
    {{ detailed_amortization_table|safe }}
    
    <h2>Combined Offset Simulation Table</h2>
    {{ combined_offset_table|safe }}
</div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    # Default parameter values
    principal_val = 590000
    annual_interest_rate_val = 3.95
    original_term_years_val = 35
    simulation_term_years_val = 15
    offset_threshold_val = 25000

    if request.method == 'POST':
        try:
            principal_val = float(request.form.get('principal', principal_val))
            annual_interest_rate_val = float(request.form.get('annual_interest_rate', annual_interest_rate_val))
            original_term_years_val = int(request.form.get('original_term_years', original_term_years_val))
            simulation_term_years_val = int(request.form.get('simulation_term_years', simulation_term_years_val))
            offset_threshold_val = float(request.form.get('offset_threshold', offset_threshold_val))
        except ValueError:
            pass  # keep defaults if conversion fails

    monthly_rate = (annual_interest_rate_val / 100) / 12
    n_original = original_term_years_val * 12
    baseline_payment = calc_baseline_payment(principal_val, monthly_rate, n_original)

    # Baseline summary: Accelerated Term Analysis Summary for terms 1 to 35
    _, baseline_summary_table = accelerated_term_analysis(principal_val, monthly_rate, original_term_years_val)
    baseline_summary_html = tabulate(baseline_summary_table, headers=["Term (years)", "Required Monthly Payment", "Extra Payment", "Total Interest", "Advanced Principal"], tablefmt="html")

    # Detailed amortization for simulation term (default 15 years)
    accelerated_payment, detailed_table = detailed_amortization(principal_val, monthly_rate, simulation_term_years_val, baseline_payment)
    detailed_amortization_html = tabulate(detailed_table, headers=["Month", "Payment", "Interest", "Principal", "Cum. Principal", "Remaining Balance", "Extra Principal", "Cum. Extra Principal"], tablefmt="html")

    # Combined offset simulation table
    combined_schedule = simulate_combined_offset_advance(principal_val, monthly_rate, accelerated_payment, baseline_payment, offset_threshold_val, simulation_term_years_val)
    combined_offset_html = tabulate(
        [
            [entry['Month'],
             f"RM{entry['Fixed Payment']:,.2f}",
             f"RM{entry['Effective Outstanding']:,.2f}",
             f"RM{entry['Interest']:,.2f}",
             f"RM{entry['Accelerated Principal']:,.2f}",
             f"RM{entry['Baseline Principal']:,.2f}",
             f"RM{entry['Extra Added']:,.2f}",
             f"RM{entry['Extra Accumulated']:,.2f}",
             f"RM{entry['Offset Applied']:,.2f}",
             f"RM{entry['Baseline Paid']:,.2f}",
             f"RM{entry['Total Offset']:,.2f}",
             f"RM{entry['Total Effective Reduction']:,.2f}",
             f"RM{entry['Remaining Principal']:,.2f}"
            ] for entry in combined_schedule
        ],
        headers=["Month", "Fixed Payment", "Effective Outstanding", "Interest", "Accelerated Principal",
                 "Baseline Principal", "Extra Added", "Extra Accumulated", "Offset Applied",
                 "Baseline Paid", "Total Offset", "Total Effective Reduction", "Remaining Principal"],
        tablefmt="html"
    )

    return render_template_string(HTML_TEMPLATE,
                                  principal=principal_val,
                                  annual_interest_rate=annual_interest_rate_val,
                                  original_term_years=original_term_years_val,
                                  simulation_term_years=simulation_term_years_val,
                                  offset_threshold=offset_threshold_val,
                                  baseline_summary=baseline_summary_html,
                                  accelerated_payment=f"RM{accelerated_payment:,.2f}",
                                  detailed_amortization_table=detailed_amortization_html,
                                  combined_offset_table=combined_offset_html)

@app.route('/shutdown', methods=['POST'])
def shutdown():
    print("Browser closed. Shutting down server...")
    os.kill(os.getpid(), signal.SIGTERM)
    return '', 200

def run_flask():
    app.run(debug=False, port=5000, use_reloader=False)

if __name__ == '__main__':
    # Open the browser automatically
    threading.Timer(0.25, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    run_flask()