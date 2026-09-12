"""
Lab #3: Baseline Chatbot vs ReAct Agent
Bản thực hành chạy offline với dữ liệu mẫu và trace có thể kiểm tra.
"""

import json
import os
import re
from typing import Dict, Any, List, Tuple
from tools import TOOL_MAP, TOOL_DEFINITIONS, get_flight_info, get_weather_forecast

SYSTEM_PROMPT = """Bạn là một ReAct Agent thông minh hỗ trợ khách hàng dịch vụ Vingroup (Vinpearl, Xanh SM, VinFast).
Bạn chỉ được sử dụng các công cụ sau:
{tools}

Quy tắc làm việc bắt buộc:
1. Khi cần thông tin, hãy suy nghĩ (Thought) và chọn Action dạng JSON chuẩn.
2. Cú pháp Action bắt buộc: Action: {{"name": "<tên tool>", "args": {{<các tham số>}}}}
3. Khi đã có đủ thông tin hoặc câu hỏi thuộc FAQ cơ bản, hãy xuất ngay Final Answer: <câu trả lời hoàn chỉnh>.
4. Nếu công cụ lỗi hai lần liên tiếp, dừng và thông báo không thể tra cứu.

Định dạng phản hồi mỗi lượt:
Thought: <suy nghĩ bước này>
Action: {{"name": "...", "args": {{...}}}}
"""

class ChatbotBaseline:
    """Baseline LLM Chatbot without ReAct Loop or Tools"""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def query(self, user_input: str) -> Dict[str, Any]:
        if self.api_key:
            try:
                from google import genai

                with genai.Client(api_key=self.api_key) as client:
                    response = client.models.generate_content(
                        model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
                        contents=f"Bạn là chatbot tư vấn du lịch. Hãy trả lời câu hỏi sau của khách hàng mà KHÔNG dùng tool hay internet: {user_input}"
                    )
                return {
                    "answer": response.text,
                    "tool_calls": [],
                    "status": "success",
                    "mode": "live_api"
                }
            except Exception:
                pass

        return {
            "answer": "Bạn có thể tìm chuyến bay trên các trang hàng không. Về thời tiết, bạn nên tra cứu trên trang dự báo thời tiết.",
            "tool_calls": [],
            "status": "success",
            "mode": "mock_baseline"
        }

class ReActAgent:
    """Mô phỏng ReAct bằng luật Python; không gọi LLM để lập kế hoạch."""
    def __init__(self, max_iterations: int = 5, api_key: str = None):
        self.max_iterations = max_iterations
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.trace: List[Dict[str, Any]] = []

    def parse_cities(self, text: str) -> List[str]:
        """Đọc địa danh theo thứ tự xuất hiện, không đảo điểm đi/đến."""
        aliases = {"HÀ NỘI": "HAN", "HỒ CHÍ MINH": "SGN", "SÀI GÒN": "SGN", "ĐÀ NẴNG": "DAD"}
        matches = re.findall(r"\b(?:HAN|SGN|DAD|HÀ NỘI|HỒ CHÍ MINH|SÀI GÒN|ĐÀ NẴNG)\b", text.upper())
        cities = []
        for match in matches:
            code = aliases.get(match, match)
            if not cities or cities[-1] != code:
                cities.append(code)
        return cities

    def parse_city_code(self, text: str) -> str:
        weather_part = re.split(r"thời tiết|nhiệt độ|mặc gì|mưa", text, maxsplit=1, flags=re.IGNORECASE)
        cities = self.parse_cities(weather_part[-1]) or self.parse_cities(text)
        return cities[-1] if cities else ""

    def execute_action(self, action_json: str, iteration: int, thought: str) -> Any:
        """Parse Action JSON, chỉ gọi tool đã đăng ký và ghi Observation."""
        action = action_json
        try:
            action = json.loads(action_json)
            if not isinstance(action, dict):
                raise ValueError("Action phải là JSON object")
            name, args = action.get("name"), action.get("args")
            if not isinstance(name, str) or not isinstance(args, dict):
                raise ValueError("Action cần name dạng chuỗi và args dạng object")
            name = name.strip().lower()
            action = {"name": name, "args": args}
            if name not in TOOL_MAP:
                raise ValueError(f"Unknown tool: {name}")
            observation = TOOL_MAP[name](**args)
        except json.JSONDecodeError:
            observation = {"error": "Invalid JSON format"}
        except Exception as exc:
            # Tool là ranh giới bên ngoài: lỗi trở thành dữ liệu cho vòng lặp.
            observation = {"error": f"{type(exc).__name__}: {exc}"}
        self.trace.append({
            "iteration": iteration, "thought": thought,
            "action": action, "observation": observation,
        })
        return observation

    def plan_and_execute_step(self, user_input: str, iteration: int) -> Tuple[str, bool]:
        """Dynamic step planning supporting multi-step, single-step, FAQ, and fallback queries"""
        user_lower = user_input.lower()
        
        # Check FAQ query (no tools needed)
        if "chính sách" in user_lower or "đổi trả" in user_lower:
            thought = "Đây là câu hỏi FAQ chung về chính sách. Không cần sử dụng tool."
            final_answer = "FAQ minh họa trong lab về Vinpearl: việc đổi/trả vé phụ thuộc điều kiện vé. Hãy kiểm tra điều kiện đặt chỗ hoặc liên hệ nơi bán vé để xác nhận chính sách thực tế."
            self.trace.append({"iteration": iteration, "thought": thought, "final_answer": final_answer})
            return final_answer, True

        # Check if flight query
        needs_flight = any(k in user_lower for k in ["chuyến bay", "vé", "bay từ", "vé máy bay"])
        needs_weather = any(k in user_lower for k in ["thời tiết", "mặc gì", "nhiệt độ", "mưa"])

        cities = self.parse_cities(user_input)
        if not needs_flight and not needs_weather:
            answer = "Xin chào! Tôi có thể tra cứu chuyến bay và thời tiết trong dữ liệu mẫu HAN, SGN, DAD."
        elif needs_flight and len(cities) < 2:
            answer = "Bạn vui lòng cung cấp điểm đi và điểm đến (HAN, SGN hoặc DAD)."
        elif needs_weather and not self.parse_city_code(user_input):
            answer = "Bạn muốn xem thời tiết tại thành phố nào: HAN, SGN hay DAD?"
        else:
            answer = None
        if answer:
            self.trace.append({"iteration": iteration, "thought": "Kiểm tra phạm vi và thông tin cần thiết.", "final_answer": answer})
            return answer, True

        # Observation quyết định bước tiếp theo; tool lỗi được thử lại.
        completed_tools = {
            step["action"]["name"] for step in self.trace
            if isinstance(step.get("action"), dict)
            and "name" in step["action"] and "observation" in step
            and not (isinstance(step["observation"], dict) and "error" in step["observation"])
        }
        if needs_flight and "get_flight_info" not in completed_tools:
            origin, destination = cities[:2]
            max_price = 5000000
            if "2 triệu" in user_lower or "2.000.000" in user_lower:
                max_price = 2000000
            elif "1.5 triệu" in user_lower or "1,5 triệu" in user_lower:
                max_price = 1500000
            elif "500k" in user_lower:
                max_price = 500000

            thought = f"Tôi cần tra cứu chuyến bay từ {origin} đi {destination} với giá tối đa {max_price} VND."
            action = {"name": "get_flight_info", "args": {"origin": origin, "destination": destination, "max_price": max_price}}
            obs = self.execute_action(json.dumps(action), iteration, thought)
            if isinstance(obs, dict) and "error" in obs:
                return obs["error"], False
            
            if not needs_weather:
                if not obs:
                    final_ans = f"Không tìm thấy chuyến bay nào từ {origin} đi {destination} với giá tối đa {max_price:,} VND."
                else:
                    lines = [f"- {fl['airline']} ({fl['flight_number']}): {fl['departure_time']} - Giá: {fl['price_vnd']:,} VNĐ" for fl in obs]
                    final_ans = f"Tìm thấy {len(obs)} chuyến bay từ {origin} đi {destination}:\n" + "\n".join(lines)
                self.trace[-1]["final_answer"] = final_ans
                return final_ans, True
                
            return f"Thought: {thought}\nAction: {json.dumps(action, ensure_ascii=False)}\nObservation: {json.dumps(obs, ensure_ascii=False)}", False

        elif needs_weather and "get_weather_forecast" not in completed_tools:
            city_code = self.parse_city_code(user_input)
            thought = f"Tôi cần kiểm tra thông tin thời tiết tại {city_code}."
            action = {"name": "get_weather_forecast", "args": {"city_code": city_code}}
            obs = self.execute_action(json.dumps(action), iteration, thought)
            if "error" in obs:
                return obs["error"], False

            if not needs_flight:
                final_ans = f"Thời tiết tại {obs.get('city', city_code)}: {obs.get('temperature_c', 'N/A')}°C, {obs.get('condition', '')}.\nGợi ý: {obs.get('recommendation', '')}"
                self.trace[-1]["final_answer"] = final_ans
                return final_ans, True
                
            return f"Thought: {thought}\nAction: {json.dumps(action, ensure_ascii=False)}\nObservation: {json.dumps(obs, ensure_ascii=False)}", False

        else:
            thought = "Tôi đã thu thập đủ thông tin để trả lời khách hàng."
            flight_obs = next((t["observation"] for t in reversed(self.trace) if t.get("action", {}).get("name") == "get_flight_info"), [])
            weather_obs = next((t["observation"] for t in reversed(self.trace) if t.get("action", {}).get("name") == "get_weather_forecast"), {})

            flight_summary = "Không tìm thấy chuyến bay phù hợp."
            if flight_obs:
                lines = [f"   - {fl['airline']} ({fl['flight_number']}): {fl['departure_time']} - Giá: {fl['price_vnd']:,} VNĐ" for fl in flight_obs]
                flight_summary = "\n".join(lines)

            weather_summary = f"Thời tiết tại {weather_obs.get('city', 'địa phương')}: {weather_obs.get('temperature_c', '')}°C ({weather_obs.get('condition', '')}).\n   - Gợi ý trang phục: {weather_obs.get('recommendation', '')}"

            final_answer = (
                f"1. Thông tin chuyến bay:\n{flight_summary}\n\n"
                f"2. Thông tin thời tiết & trang phục:\n   - {weather_summary}"
            )
            self.trace.append({
                "iteration": iteration,
                "thought": thought,
                "final_answer": final_answer
            })
            return final_answer, True

    def run(self, user_input: str) -> Dict[str, Any]:
        self.trace = []
        iteration = 1
        consecutive_errors = 0
        
        while iteration <= self.max_iterations:
            result, is_final = self.plan_and_execute_step(user_input, iteration)
            observation = self.trace[-1].get("observation", {}) if self.trace else {}
            failed = isinstance(observation, dict) and "error" in observation
            consecutive_errors = consecutive_errors + 1 if failed else 0
            if consecutive_errors >= 2:
                answer = "Không thể tra cứu vì công cụ lỗi hai lần liên tiếp. Vui lòng thử lại sau."
                self.trace[-1]["final_answer"] = answer
                return {"answer": answer, "trace": self.trace, "iterations": iteration, "status": "tool_error"}
            if is_final:
                return {
                    "answer": result,
                    "trace": self.trace,
                    "iterations": iteration,
                    "status": "completed"
                }
            iteration += 1

        answer = "Không thể hoàn thành trong số bước tối đa (Max Iterations Safeguard)."
        if self.trace:
            self.trace[-1]["final_answer"] = answer
        return {
            "answer": answer,
            "trace": self.trace,
            "iterations": iteration - 1,
            "status": "max_iterations_reached"
        }

def main():
    user_query = "Tìm cho tôi chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết SGN nên mặc gì?"
    
    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))
    
    print("\n=== RUNNING REACT AGENT ===")
    agent = ReActAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result)
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
