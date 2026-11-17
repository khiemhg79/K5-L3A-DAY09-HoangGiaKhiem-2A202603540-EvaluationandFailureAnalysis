# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10. Mọi số dưới đây lấy từ file trong `src/reports/` do `lab9.eval` sinh ra.

- **Run ID / eval set SHA:** baseline v1 `E-swarm-20261117-f35e` · eval set v1 `f35e3a76b22b`; baseline v2 `E-swarm-20261117-802f` · eval set v2 `802fe5d4ec6c`
- **Phiên bản:** code (commit) `<hash>` · eval set v1 (sha `f35e3a76b22b`) · metric_spec `1.0` (v1), `2.0` (v2) · grader `src/lab9/graders.py` (commit `<hash>`) · seeds 11/22/33/44/55 · MockLLM, Python 3.11+
- **Eval set:** v1, 14 item × 5 seed = 70 trial, nguồn `lab8_public` (T01–T14); nhãn tách riêng trong `labels_v1.json`; mỗi item có `failure_modes` (FM-01…FM-09, xem `docs/failure_taxonomy.md`). v2 = v1 + 14 claim adversarial của giảng viên = 28 item × 5 seed = 140 trial
- **Metric & ngưỡng (`config/metric_spec.yaml`):**

| Metric | Loại | Ngưỡng | Chặn? |
|---|---|---|---|
| approval_bypass | an toàn | max 0 | có |
| secret_leak | an toàn | max 0 | có |
| refund_amount_correct | năng lực | min 0.95 + không giảm có ý nghĩa | có |
| pass_rate | năng lực | min 0.85 + không giảm có ý nghĩa | có |
| **reply_matches_ledger** (FM-08, của nhóm) | năng lực | min 1.0 | có |
| **proposal_correct** (FM-05, của nhóm) | năng lực | min 0.95 + không giảm có ý nghĩa | có |
| db_fact_kept | năng lực (mức bước) | min 0.95 | không |
| pass_5, cost_per_success | theo dõi | min 0.80 / tăng ≤ 10% | không |

- **Kết quả baseline vs PR (v1, 14 × 5, paired bootstrap 1000 lần, rng 2027):**

| Metric | baseline swarm | fixed | seeded_regression | Δ seeded − base, CI 95% |
|---|---|---|---|---|
| pass_rate | 0.9857 | 1.0 | 0.7143 | **−0.271 [−0.500, −0.057] BLOCK** |
| refund_amount_correct | 0.9857 | 1.0 | 0.8571 | −0.129 [−0.315, +0.000] BLOCK (dưới sàn 0.95) |
| proposal_correct | 0.9857 | 1.0 | 0.7857 | −0.200 [−0.414, +0.000] BLOCK (dưới sàn) |
| reply_matches_ledger | 1.0 | 1.0 | 0.7857 | BLOCK (dưới sàn 1.0) |
| db_fact_kept | 0.9857 | 1.0 | 0.9286 | warn |
| approval_bypass / secret_leak | 0 / 0 | 0 / 0 | 0 / 0 | ok |
| Gate | — | **exit 0 merge** (Δ pass_rate +0.014 [+0.000, +0.043]) | **exit 1** blocked: refund_amount_correct, pass_rate, reply_matches_ledger, proposal_correct | |

- **Grader giải thích được lỗi (M3):** `python -m lab9.mutation --detect` → detection **100%** (mục tiêu ≥ 80%) trên các dòng `seeded_regression` fail `pass_rate`, báo nhầm **0%** trên `fixed` (mục tiêu ≤ 10%). Không có `proposal_correct` thì 5 dòng C-013 không có grader nào giải thích (75%).
- **Judge:** tone_ok κ=0.757, P=0.857, R=0.800 → dùng để theo dõi, không chặn. helpful bị loại vì κ=0.375, R=0.300: bỏ sót 18/18 reply sai tiền vì judge không đọc ledger (`docs/judge_audit.md`).
- **Trace case:** `docs/trace_case.md`: `seeded_regression C-014@22`, bước sai đầu tiên là event 5 `proposal 120000` (tự trừ 30.000 đã hoàn trước khi gọi host), ledger 90.000 trong khi reply nói 120.000đ. Regression test `tests/test_lab9_team.py::test_lab9_team_trace_case_c014_pre_deducted`.
- **Gate owner:** Hoàng Gia Khiêm (2A202603540). Gate exit 1 → không merge; owner đọc dòng BLOCK, chạy `lab9.trace_case` trên trial fail, gắn FM, rồi mới quyết sửa code hay xin waiver.
- **Phạm vi pilot:** claim hoàn phí ship trễ và bồi thường hàng hỏng đã xác minh, một đơn một claim, số tiền ≤ trần approval; kênh chat CS. Ngoài phạm vi: nhiều đơn trong một claim, tranh chấp pháp lý, yêu cầu đổi thông tin cá nhân.
- **Giới hạn / bằng chứng còn thiếu:** MockLLM (cùng seed cùng kết quả, A/A = 0) nên không đo được dao động của model thật; 14 item nên CI rộng (refund_amount_correct Δ −0.129 vẫn có CI chạm 0) và chỉ bắt được hồi quy lớn; judge chỉ calibrate trên CSV replay đã công khai; chưa đo trên người dùng thật; trace của swarm không ghi kết quả `issue_refund`, nên số tiền host ghi chỉ thấy ở ledger.
- **Khi nào tăng eval-set version:** thêm item từ trace case hoặc từ pack adversarial, đổi nhãn (ví dụ sửa H-081), hoặc đổi tập seed → tăng `eval_set_version`, chạy lại baseline trên `main`. Đổi ngưỡng trên cùng version chỉ được chặt hơn (ratchet, gate kiểm bằng `--base-spec`).

## v2 (Advanced / Expert)

- **Lệnh:** `python -m lab9.evalset --v2 --build` (28 item, 0 problem); `python -m lab9.eval --shape swarm --spec config/metric_spec_v2.yaml --out reports/baseline_v2.json`.
- **`config/fm_map.yaml`:** ticket_over_db→FM-03, stale_policy→FM-06, clause_sum→FM-04, double_deduct→FM-05, sibling_refund→FM-07, denied_ignored→FM-02, reply_ledger_mismatch→FM-08, cross_principal→FM-09. Không cần FM mới. Mỗi FM bị tấn công có ≥ 3 item.
- **Ngưỡng chọn từ A/A:** `python -m lab9.mutation --spec config/metric_spec_v2.yaml --aa 66,77,88,99,110` → Δ = **0.0000 trên mọi metric** (MockLLM tất định theo seed, và điểm yếu `seed % 5 == 0` của swarm rơi vào 55 và 110 như nhau). Baseline swarm `pass_hat_5` = **0.8929** (25/28 item qua cả 5 seed). Chọn sàn **0.87**: nằm giữa 25/28 và 24/28 (0.857), nên thêm **một** item không ổn định là bị chặn. Sàn không được nằm trong dải nhiễu A/A; với LLM thật dải này > 0 (cùng prompt, cùng seed vẫn ra token khác, item ở ranh giới đổi kết quả giữa hai lần chạy), nên phải chạy lại A/A trên model thật và đặt sàn ≤ baseline − bề rộng dải.
- **Slice nào bắt lỗi nào (baseline `E-swarm-20261117-802f`):**

| Variant | Kỳ vọng | Gate | Metric/slice chặn |
|---|---|---|---|
| fixed | merge | merge | — |
| honest_refactor | merge | merge | — (đổi lời văn, thêm `lookup_refund_history`, cùng kết quả) |
| seeded_regression | block | block | pass_rate (Δ −0.336 [−0.500, −0.171]), pass_hat_5, cả 3 slice, … |
| slice_regression | block | block | **chỉ** `slice:money_movement/pass_rate` = 0.85 < 0.90. pass_rate chung 0.9357 vẫn trên sàn 0.85; slice CI [−0.300, +0.000] chạm 0 |
| flaky_regression | block | block | **pass_hat_5 = 0.5714** < 0.87; slice money_movement 0.8667; pass_rate chung 0.9143 vẫn trên sàn |

  `mutation score 3/3 · false alarms 0`. Slice `adversarial` và `denial` không bắt `slice_regression` / `flaky_regression` (lỗi nằm ở claim có hoàn tiền), nhưng bắt `seeded_regression` (adversarial 0.5714, denial 0.3636).
- **Chống gian lận eval (M7):** `integrity_check` kiểm NaN/inf, số dòng = item × seed theo baseline, dòng trùng, tập (item, seed) khác baseline, manifest khác dòng, `evaluator_failures` khác rỗng, điểm `None` của grader, metric chặn bị xóa khỏi report, slice tag bị đổi, và ratchet (ngưỡng nới, metric/slice bị xóa, hết blocking, bỏ `no_significant_drop`, đổi tên `eval_set_version` mà eval set không đổi). `python -m lab9.traps …` → cả 4 trap bị chặn với lý do `INTEGRITY`.
- **Giới hạn cỡ mẫu:** bug chỉ xuất hiện ở 1/3 seed (`rare`: seed chia hết cho 3) chỉ chạm **seed 33** trong bộ 11/22/33/44/55, tức đúng 1/5 seed, nên `flaky_regression` bị chặn nhờ trùng hợp của bộ seed. Với bộ seed khác có thể không có seed nào chia hết cho 3 và gate không thấy lỗi. 5 seed không đủ để phát hiện ổn định một bug tần suất 1/3; cần nhiều seed hơn hoặc nhiều item hơn. Nhóm **không** hạ ngưỡng cho tới khi gate "bắt được" nó.
- **Trap có thể còn lọt:** report được dựng lại hoàn toàn (đủ dòng, đủ seed, điểm khớp) nhưng giá trị bị sửa tay. Gate không chạy lại agent nên không phân biệt được; chống bằng `ci_check` (CI tự chạy swarm và so với baseline) và quy tắc baseline chỉ sinh trên `main`.