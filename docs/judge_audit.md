# Judge audit

Chạy:

```bash
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 8
```

FAIL là lớp dương (judge có nhiệm vụ tìm lỗi). Output thật:

```
tone:    n=100 P=0.857 R=0.8 kappa=0.757 {'tp': 24, 'fp': 4, 'fn': 6, 'tn': 66}
         fail rate observed 0.28 -> corrected 0.3                    PASS floors
helpful: n=100 P=1.0 R=0.3 kappa=0.375 {'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}
         fail rate observed 0.09 -> corrected 0.3                    FAIL floors
```

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt cả 3 | **dùng**, chỉ để theo dõi giọng văn, không chặn tiền |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Trượt κ và R | **loại** |

## ≥5 case audit thủ công

10 bất đồng của `tone_ok` (6 FN + 4 FP) và 3 mẫu đại diện của `helpful`:

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric thêm: xưng hô phải là "anh/chị", "LogiX" |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Xưng "bạn" với khách. Cùng luật xưng hô như #1 |
| 3 | H-029 "…Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Giọng ra lệnh; judge chỉ thấy "Dạ, vui lòng". Rubric thêm: không ra lệnh, không cấm khách liên hệ |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric sửa: xin lỗi **không bắt buộc** khi trả lời đủ ý và lịch sự |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Rubric ghi rõ danh sách từ tiếng Anh được phép |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống. Đây là lỗi nội dung hơn là giọng: chuyển sang grader code (FM-08, số trong reply phải bằng ledger) chứ không trông vào judge tone |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji trong ngữ cảnh khiếu nại. Rubric thêm: không emoji |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Nhãn người sai (đọc nhầm ticket). **Sửa nhãn** thành FAIL trước lần calibrate sau; không sửa rubric |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người | Lặp "Dạ" do lỗi gõ: không phải lỗi giọng. Rubric ghi: lỗi gõ nhẹ không làm FAIL tone |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric thêm: reply phải có dấu đầy đủ |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (helpful) | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge không thấy ledger nên không thể biết sai tiền |
| 12 | HL-016 xin lỗi 2 lần + "đã hoàn 55.000đ" (helpful) | PASS | FAIL | Người | Ledger 35.000đ. Judge chấm "lịch sự, đầy đủ" theo độ dài và lời xin lỗi |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." (helpful) | PASS | FAIL | Người | Sai xưng hô, không nói số tiền: judge vẫn cho là "hữu ích" |

## Kết luận

- **`helpful` bị loại, không dùng làm gate.** Ma trận nhầm lẫn: tp 9, fp 0, **fn 21**, tn 70. Recall 0.30: judge bỏ sót 21/30 reply người đánh FAIL, trong đó **18/21 là "sai tiền"** (cột `human_failure`), 3/21 là "sai xưng hô". 9 case judge bắt được đều là lỗi nhìn thấy trên chữ (giọng cụt 4, không hỏi lại mã đơn 3, lạc đề 2); judge bỏ sót **cả 18/18** reply sai tiền. Precision 1.0 không cứu được: một gate chỉ bắt 30% lỗi thì để lọt 70%. κ 0.375 < 0.6. Nguyên nhân gốc: judge chỉ đọc reply, **không đọc ledger**, nên không thể biết số tiền đúng hay sai; reply càng dài và xin lỗi nhiều thì judge càng cho PASS. Tiền phải chấm bằng code (`reply_matches_ledger`, `refund_amount_correct`).
- **Rogan-Gladen cho thấy rủi ro:** tỉ lệ fail quan sát được của `helpful` là 0.09, sau hiệu chỉnh là 0.30. Dùng judge này thì báo cáo sẽ nói "9% reply không hữu ích" trong khi thực tế khoảng 30%.
- **`tone_ok` dùng được nhưng chỉ để theo dõi:** đạt cả 3 sàn. 9/10 bất đồng người đúng; 1 case (H-081) judge đúng và nhãn người phải sửa. Tỉ lệ fail 0.28 → 0.30 sau hiệu chỉnh. Không đặt `tone_ok` làm metric chặn, vì tone không quyết định tiền và recall 0.8 vẫn bỏ sót 20%.
- **Sửa rubric tone:** xưng "anh/chị" và "LogiX" (cấm "em", "bạn"); không ra lệnh; không emoji; phải có dấu; xin lỗi không bắt buộc; cho phép từ "refund"; lỗi gõ nhẹ không fail. Hứa hẹn về tiền thì để grader code chấm.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật. Sau khi sửa rubric phải calibrate lại trên tập mới, không dùng lại 100 dòng này (đã nhìn thấy).