# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 22
python -m lab9.trace_case --shape fixed --claim C-014 --seed 22   # đối chứng
```

## Case: `seeded_regression` C-014@22 (T14, hoàn phần chênh)

Output thật của lệnh trên:

```
== seeded_regression C-014@22  lab8 grader: FAIL (proposal_mismatch)
-- trace (step, kind, payload)
   1 handoff            {"request_id": "REQ-C-014", "allowed_tools": ["lookup_order", "lookup_policy", "compute_compensation"], ...
   2 investigator       {"lookup_order": {"visible": true, "reason": "ok", "order": {"order_id": "O-515", "status": "delivered_late", ...
   3 quote              {"amount_vnd": 150000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03", "DMG-04"], ...
   4 refund_history     {"refund_count": 1, "refunded_vnd": 30000}
   5 proposal           {"amount_vnd": 120000}
   6 reply              {"text": "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."}
-- ledger vs label
  refund_vnd     ledger=90000    label=120000   <-- differs
  refund_count   ledger=1        label=1
  status         result=resolved label=resolved
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@22`, item `E-014`, report `reports/eval_seeded_regression.json` (run `E-seeded_regression-20261117-f35e`) |
| Triệu chứng | `pass_rate`, `refund_amount_correct`, `proposal_correct`, `reply_matches_ledger` cùng fail. Reply nói **120.000đ**, đúng bằng nhãn, nên đọc reply thì tưởng đúng. Ledger chỉ ghi **90.000**. Status `resolved` cũng đúng nhãn |
| Bước sai đầu tiên | **Event 5 `proposal`** `{"amount_vnd": 120000}`: agent lấy quote 150.000 trừ 30.000 đã hoàn rồi mới đưa cho host |
| Vì sao là bước *đầu tiên* | Event 1–2 đúng (handoff chỉ có tool đọc, đơn O-515 thấy được và đúng chủ). Event 3 đúng: `compute_compensation` ra 150.000 (SHIP-LATE-03 + DMG-04, lấy max theo policy). Event 4 là một lần đọc hợp lệ (`lookup_refund_history` là tool đọc; `fixed` không gọi nhưng `honest_refactor` gọi mà vẫn đúng). Sai bắt đầu khi số đọc ở event 4 được **dùng để trừ** ở event 5. Host sau đó trừ tiếp 30.000 theo trần đơn: 120.000 − 30.000 = 90.000 |
| Failure mode | **FM-05** pre_deducted (kéo theo FM-08: reply nói số agent tự tính, không phải số host ghi) |
| Đối chứng | `fixed C-014@22`: event 3 `quote 150000` → không có event `proposal` (đưa nguyên quote cho host) → event 4 `reply` "đã hoàn 120.000đ", ledger 120.000, Lab 8 grader PASS |
| Regression test | `src/tests/test_lab9_team.py::test_lab9_team_trace_case_c014_pre_deducted`: chạy lại cả hai shape, assert event thứ 5 là `proposal 120000`, và `RefundAmountCorrect`, `ProposalCorrect`, `ReplyMatchesLedger` đều fail trên `seeded_regression`, đều pass trên `fixed`. Đã chạy: pass. Item đã có sẵn trong eval set (`E-014`, `failure_modes: [FM-04, FM-05, FM-08]`) nên gate cũng bắt nó (`proposal_correct` Δ −0.200 → BLOCK) |
| Chưa chắc chắn | Trace không ghi lời gọi `issue_refund` và kết quả của host, nên con số 90.000 chỉ thấy ở ledger, không thấy trong trace. Trace cũng không cho biết agent trừ vì "hiểu sai luật" hay vì prompt: chỉ chứng minh được bước nào dùng số sai. Reply trùng nhãn là trùng hợp của case này (120.000 = 150.000 − 30.000): ở C-008 reply và nhãn khác nhau |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai. Case này là ví dụ rõ nhất: reply đúng nhãn nhưng ledger sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.