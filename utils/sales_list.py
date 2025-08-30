import csv
from datetime import date
from django.utils.timezone import now
from finance.models import Sale, SaleItem  


def export_sales_to_csv(day: int, month: int, year: int = None, filepath: str = None):
    """
    Export all sales (and their items) for a given day/month/year into a CSV file.
    If no year is provided, defaults to current year.
    """
    today = date.today()
    year = year or today.year

    try:
        target_date = date(year, month, day)
    except ValueError:
        raise ValueError("Invalid date provided.")

    sales = Sale.objects.filter(date=target_date).prefetch_related("saleitem_set")

    if not filepath:
        filepath = f"sales_{target_date}.csv"

    with open(filepath, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # CSV headers
        writer.writerow([
            "Sale ID", "Receipt Number", "Date", "Cashier", "Branch",
            "Meal", "Dish", "Product",
            "Quantity", "Price", "Subtotal",
            "Total Amount", "Tax", "Amount Paid", "Change", "Cash Type", "Staff"
        ])

        for sale in sales:
            for item in sale.saleitem_set.all():
                writer.writerow([
                    sale.id,
                    sale.receipt_number,
                    sale.date,
                    sale.cashier.username,
                    item.meal.name if item.meal else "",
                    item.dish.name if item.dish else "",
                    item.product.name if item.product else "",
                    item.quantity,
                    float(item.price),
                    float(item.price) * item.quantity,
                    float(sale.total_amount),
                    float(sale.tax),
                    float(sale.amount_paid),
                    float(sale.change),
                    sale.cash_type,
                    sale.staff,
                ])

    return filepath
