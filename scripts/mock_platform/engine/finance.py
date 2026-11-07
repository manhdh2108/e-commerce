"""Settlement from immutable line policy snapshots, with per-line ownership ledger."""

from datetime import date, datetime, timedelta

from .domain import NotEligible


class FinanceWorkflow:
    def __init__(self, engine):
        self.e, self.u = engine, engine.u

    def execute(self):
        e, c = self.e, self.e.code
        if c == "FIN-POL-01":
            if e.p.get("scope") == "all_leaf":
                categories = [
                    r
                    for r in self.u.rows("categories")
                    if not any(
                        x["parent_id"] == r["id"] for x in self.u.rows("categories")
                    )
                ]
            else:
                categories = [self.u.one("categories", e.p.get("category"))]
            if not categories or not all(categories):
                raise NotEligible("Cần danh mục có thật để tạo chính sách.")
            start, end = e.p.get("start") or e.now[:10], e.p.get("end") or None
            if end and end < start:
                raise NotEligible("Ngày kết thúc trước ngày bắt đầu.")
            created = 0
            for cat in categories:
                matching = [
                    r
                    for r in self.u.rows("seller_commission_rates")
                    if r["category_id"] == cat["id"]
                    and r["seller_tier"] == e.p["tier"]
                    and r["effective_from"] == start
                    and r["effective_to"] == end
                    and r["commission_rate"] == e.p["rate"] / 100
                ]
                if matching:
                    continue
                if any(
                    r["category_id"] == cat["id"]
                    and r["seller_tier"] == e.p["tier"]
                    and (not r["effective_to"] or r["effective_to"] >= start)
                    and (not end or r["effective_from"] <= end)
                    for r in self.u.rows("seller_commission_rates")
                ):
                    raise NotEligible(
                        "Khoảng chính sách chồng lấn; không ghi một phần danh sách."
                    )
                self.u.add(
                    "seller_commission_rates",
                    category_id=cat["id"],
                    seller_tier=e.p["tier"],
                    commission_rate=e.p["rate"] / 100,
                    effective_from=start,
                    effective_to=end,
                )
                created += 1
            if not created:
                raise NotEligible("Các chính sách yêu cầu đã tồn tại; không tạo trùng.")
            return
        if c == "FIN-POL-02":
            previous = e.choose("seller_commission_rates")
            start = e.p.get("start")
            if not start or start <= e.now[:10] or start <= previous["effective_from"]:
                raise NotEligible("Chính sách mới chỉ được bắt đầu trong tương lai.")
            end = e.p.get("end") or None
            if end and end < start:
                raise NotEligible("Khoảng chính sách không hợp lệ.")
            if any(
                r["id"] != previous["id"]
                and r["category_id"] == previous["category_id"]
                and r["seller_tier"] == previous["seller_tier"]
                and (not r["effective_to"] or r["effective_to"] >= start)
                and (not end or r["effective_from"] <= end)
                for r in self.u.rows("seller_commission_rates")
            ):
                raise NotEligible("Chính sách mới chồng kỳ khác.")
            if not previous["effective_to"] or previous["effective_to"] >= start:
                e.touch(
                    "seller_commission_rates",
                    previous,
                    effective_to=(
                        date.fromisoformat(start) - timedelta(days=1)
                    ).isoformat(),
                )
            return self.u.add(
                "seller_commission_rates",
                category_id=previous["category_id"],
                seller_tier=previous["seller_tier"],
                commission_rate=e.p["rate"] / 100,
                effective_from=start,
                effective_to=end,
            )
        if c == "FIN-REC-01":
            start = e.p.get("start") or "0001-01-01"
            end = e.p.get("end") or e.now[:10]
            if end > e.now[:10] or end < start:
                raise NotEligible("Kỳ đối soát không hợp lệ hoặc ở tương lai.")
            settled = {r["order_item_id"] for r in self.u.rows("seller_payout_items")}
            lines = []
            for line in self.u.rows("order_items"):
                order = self.u.one("orders", line["order_id"])
                if (
                    not order
                    or not order["completed_at"]
                    or order["order_status"] != "Completed"
                    or line["id"] in settled
                    or line["commission_rate"] is None
                ):
                    continue
                frozen = e.getmeta(f"order:{order['id']}", {}).get("policy", e.policy)
                if not start <= order["completed_at"][
                    :10
                ] <= end or datetime.fromisoformat(order["completed_at"]) + timedelta(
                    days=frozen["payout_hold_days"]
                ) > datetime.fromisoformat(e.now):
                    continue
                returned = [
                    r
                    for r in self.u.rows("returns")
                    if r["order_item_id"] == line["id"]
                ]
                if any(r["status"] not in ["Rejected", "Refunded"] for r in returned):
                    continue
                paid = sum(
                    p["paid_amount"]
                    for p in self.u.rows("payments")
                    if p["order_id"] == order["id"] and p["payment_status"] == "Success"
                )
                if paid < order["final_amount"]:
                    continue
                lines.append(
                    (
                        line,
                        order,
                        sum(
                            r["refund_amount"]
                            for r in returned
                            if r["status"] == "Refunded"
                        ),
                    )
                )
            # Một seller chỉ có một kỳ đối soát kết thúc trong cùng ngày: dòng đủ điều kiện muộn hơn
            # trong ngày (hết thời gian giữ tiền sau lượt đối soát đầu) chờ kỳ của ngày sau. Nếu không,
            # (seller_id, period_start, period_end) bị trùng → vi phạm unique (sự cố 07/11/2026, ngày mô phỏng 14/01).
            settled_today = {
                r["seller_id"]
                for r in self.u.rows("seller_payouts")
                if r["period_end"] == end
            }
            sellers = sorted(
                {
                    o["seller_id"]
                    for _, o, _ in lines
                    if (
                        not e.p.get("target")
                        or str(o["seller_id"]) == str(e.p["target"])
                    )
                    and o["seller_id"] not in settled_today
                }
            )
            if not sellers:
                raise NotEligible(
                    "Không có dòng đủ kỳ giữ tiền, đủ thu, đủ policy và đã kết thúc nghĩa vụ trả/hoàn."
                )
            seller = e.r.choice(sellers)
            selected = [(i, o, r) for i, o, r in lines if o["seller_id"] == seller]
            payout = self.u.add(
                "seller_payouts",
                seller_id=seller,
                period_start=min(o["completed_at"][:10] for _, o, _ in selected),
                period_end=end,
                gross_sales=0,
                refund_amount=0,
                commission_amount=0,
                payout_amount=0,
                payout_status="Pending",
            )
            e.meta(f"last_transition:seller_payouts:{payout['id']}", e.now)
            gross = refunds = commission = net = 0
            for line, _, refund in selected:
                subsidy = sum(
                    p["applied_discount_amount"]
                    for p in self.u.rows("order_item_promotions")
                    if p["order_item_id"] == line["id"] and p["funded_by"] == "Platform"
                )
                seller_gross = round(line["net_amount"] + subsidy, 2)
                returned_quantity = sum(
                    r["quantity"]
                    for r in self.u.rows("returns")
                    if r["order_item_id"] == line["id"] and r["status"] == "Refunded"
                )
                seller_refund = round(
                    seller_gross * returned_quantity / line["quantity"], 2
                )
                fee = round((seller_gross - seller_refund) * line["commission_rate"], 2)
                amount = round(seller_gross - seller_refund - fee, 2)
                self.u.add(
                    "seller_payout_items",
                    seller_payout_id=payout["id"],
                    order_item_id=line["id"],
                    gross_amount=seller_gross,
                    refund_amount=seller_refund,
                    commission_amount=fee,
                    net_amount=amount,
                    created_at=e.now,
                )
                gross += seller_gross
                refunds += seller_refund
                commission += fee
                net += amount
            return e.touch(
                "seller_payouts",
                payout,
                gross_sales=round(gross, 2),
                refund_amount=round(refunds, 2),
                commission_amount=round(commission, 2),
                payout_amount=round(net, 2),
            )
        if c == "FIN-REC-02":
            payout = e.choose(
                "seller_payouts", lambda r: r["payout_status"] == "Pending"
            )
            lines = [
                r
                for r in self.u.rows("seller_payout_items")
                if r["seller_payout_id"] == payout["id"]
            ]
            if (
                not lines
                or abs(sum(r["net_amount"] for r in lines) - payout["payout_amount"])
                > 0.01
            ):
                raise NotEligible("Đối soát không khớp ledger dòng; chưa duyệt.")
            e.meta(f"last_transition:seller_payouts:{payout['id']}", e.now)
            return e.touch("seller_payouts", payout, payout_status="Approved")
        if c == "FIN-PAY-01":
            payout = e.choose(
                "seller_payouts", lambda r: r["payout_status"] == "Approved"
            )
            from .outcomes import ProviderAttempt

            if not ProviderAttempt(e).succeed("seller_payouts", payout):
                return
            return e.touch(
                "seller_payouts", payout, payout_status="Paid", paid_at=e.now
            )
        if c == "FIN-SEL-01":
            return e.choose("seller_payouts")
        raise NotEligible("Hành động tài chính chưa được hỗ trợ.")
