import { AIMessage } from "./types";

export class LLMService {
  private API_BASE_URL = "http://127.0.0.1:8000/";

  async sendMessage(conversation: AIMessage[]): Promise<AIMessage> {
    return new Promise<AIMessage>((resolve, reject) => {
      fetch( this.API_BASE_URL + "api/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ conversation }),
      })
        .then((res) => res.json())
        .then((data) => {
          resolve(data);
        })
        .catch((err) => {
          console.error("Error fetching response:", err);
          reject(err);
        });
    });
  }
}
