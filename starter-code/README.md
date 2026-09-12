# Lab #3 — Chatbot Baseline và ReAct Agent

Bản hoàn thiện chạy offline với dữ liệu mẫu. Mục tiêu là hiểu cách agent chọn
công cụ, sử dụng kết quả tra cứu và dừng đúng lúc.

## 1. Chạy bài lab

Thực hiện tại thư mục gốc `Vinuni-Codelab-Day3` (thư mục cha của file này).
Môi trường `.venv` đã được tạo trên máy hiện tại. Khi cài lại từ đầu:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r starter-code/requirements.txt
```

Chạy demo và bộ chấm:

```bash
source .venv/bin/activate

env -u GEMINI_API_KEY python starter-code/template.py
env -u GEMINI_API_KEY python -m pytest autograder -v
```

`env -u GEMINI_API_KEY` chỉ bỏ biến API key trong tiến trình chạy lệnh đó,
đảm bảo baseline chạy offline. Không cần API key cho bài thực hành này.
Kết quả kiểm thử: **24 passed** (8 test gốc + 16 trường hợp bổ sung).

## 2. Mỗi file làm gì?

| File | Vai trò |
|---|---|
| `template.py` | Baseline, chọn bước xử lý, thực thi Action, vòng lặp và demo |
| `tools.py` | Hai hàm đọc dữ liệu và `TOOL_MAP` ánh xạ tên → hàm |
| `../raw-data/flight_data.json` | Các chuyến bay mẫu |
| `../raw-data/weather_data.json` | Thời tiết và gợi ý trang phục mẫu |
| `../raw-data/customer_queries.json` | 5 câu hỏi để thử |
| `../autograder/test_agent.py` | 8 test gốc, được giữ nguyên |
| `../autograder/test_safeguards.py` | Test chiều bay, JSON, lỗi tool, giới hạn lượt và trace |

## 3. Giải thích 4 milestone

### Milestone 1 — Baseline

`ChatbotBaseline.query()` trả dictionary gồm `answer`, `tool_calls`, `status`,
`mode`. Ở chế độ mock, câu trả lời chỉ hướng dẫn người dùng tự tra cứu,
`tool_calls` rỗng. Baseline không đọc hai file dữ liệu.

### Milestone 2 — Tool registry

`get_flight_info("HAN", "SGN", 2000000)` lọc chuyến bay theo điểm đi,
điểm đến và giá **nhỏ hơn hoặc bằng** ngân sách. Kết quả là danh sách.
`get_weather_forecast("SGN")` trả dictionary thời tiết.

`TOOL_MAP` là danh bạ hàm. Ví dụ `TOOL_MAP["get_weather_forecast"]`
lấy ra hàm Python tương ứng để gọi với `city_code="SGN"`.

### Milestone 3 — Vòng lặp ReAct

Với câu hỏi “Tìm chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết
SGN nên mặc gì?”, agent thực hiện:

| Lượt | Action | Observation / kết quả |
|---|---|---|
| 1 | `get_flight_info` | VN213: 1.850.000 VNĐ; VJ151: 1.450.000 VNĐ |
| 2 | `get_weather_forecast` | SGN: 32°C, mưa; mang ô và quần áo thoáng mát |
| 3 | Tổng hợp | Trả thông tin chuyến bay và thời tiết, `completed` |

Mỗi phần tử `trace` ghi `iteration`, `thought` (mô tả bước), `action`,
`observation`; bước kết thúc có `final_answer`. Bước trả lời trực tiếp có thể
không có Action/Observation. Câu hỏi chỉ cần một tool kết thúc trong một lượt;
FAQ kết thúc mà không gọi tool.

Agent xem các Observation đã thành công để quyết định bước tiếp theo.
Vì vậy khi một tool lỗi tạm thời, nó thử lại tool đó thay vì bỏ qua bước.

### Milestone 4 — Safeguards

- `execute_action()` dùng `json.loads()`, không thực thi chuỗi code.
- Tên tool được `.strip().lower()` rồi tra trong `TOOL_MAP`.
- JSON sai, tên tool lạ, tham số không hợp lệ hoặc exception từ tool trở
  thành Observation có `error`.
- Hai lỗi liên tiếp: dừng với `tool_error`.
- Hết lượt mà chưa hoàn thành: `max_iterations_reached`.
- Mỗi lần `run()` tạo trace mới, không trộn kết quả câu hỏi trước.
- Danh sách chuyến bay rỗng là kết quả hợp lệ, không phải lỗi công cụ.

## 4. Tự thử và giải thích kết quả

Thay `user_query` trong `main()` của `template.py`, rồi chạy lại demo:

1. `Có chuyến bay nào từ HAN đi DAD giá dưới 1.5 triệu không?`
   → QH202, 1.200.000 VNĐ, một lượt.
2. `Thời tiết ở Đà Nẵng DAD hiện tại thế nào?`
   → Dữ liệu mẫu 28°C, một lượt.
3. `Tìm cho tôi chuyến bay từ SGN đi HAN dưới 500k.`
   → Không tìm thấy; trace phải giữ đúng chiều SGN → HAN.
4. Đổi `ReActAgent(max_iterations=5)` trong `main()` thành `max_iterations=2`
   và chạy câu hỏi gốc cần cả chuyến bay lẫn thời tiết.
   → Hai tool đã chạy nhưng chưa có lượt tổng hợp, nên agent trả
   `max_iterations_reached`. Đổi về 5 sau khi thử.

Bạn có thể trình bày bài bằng câu: “Baseline trả lời mà không tra cứu;
agent dùng tool lấy dữ liệu, ghi lại các bước và có điều kiện dừng.”

## 5. Phạm vi của bản lab

Đây là mô phỏng bằng luật Python, chưa phải agent dùng LLM để chọn tool.
`SYSTEM_PROMPT` và `TOOL_DEFINITIONS` giữ vai trò tài liệu cho bước tích hợp
model sau này; `ReActAgent` chưa gửi chúng tới API. Nhánh Gemini có sẵn trong
baseline không thuộc phần kiểm thử offline và chưa được xác minh chạy live.
Nhánh này dùng SDK `google-genai` (`from google import genai`), đã khai báo
trong `requirements.txt`. Model mặc định là `gemini-3.8-flash`; có thể đổi qua
biến môi trường `GEMINI_MODEL`. API key được đọc từ `GEMINI_API_KEY`.

Bộ đọc câu hỏi hỗ trợ các mẫu trong lab: HAN/SGN/DAD hoặc tên tiếng Việt,
điểm đi xuất hiện trước điểm đến; ngân sách 2 triệu, 1.5/1,5 triệu, 500k
(mặc định 5 triệu). Nó chưa hiểu mọi cách diễn đạt, lịch bay hay ngày đi.
FAQ chính sách được ghi rõ là minh họa. Dữ liệu chuyến bay và thời tiết là
JSON tĩnh, không dùng làm thông tin đặt vé hoặc dự báo thực tế.
