# AI Chat Bot

A real-time chat application powered by OpenAI's API. This is the first application in the **AI Engineer Path** series, demonstrating full-stack development with AI integration.

## ✨ Key Features

- **Interactive Chat Interface** - Send and receive messages in real-time
- **OpenAI Integration** - Powered by OpenAI's GPT models for intelligent responses
- **Conversation History** - Maintains full conversation context for coherent discussions
- **Responsive Design** - Works seamlessly on desktop and mobile devices
- **Error Handling** - Graceful error messages and retry mechanisms
- **CORS-enabled Backend** - Properly configured for frontend integration
- **Auto-generated API Docs** - Swagger UI available at `/docs`

## 🛠️ Tech Stack

- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS
- **Backend:** FastAPI (Python), OpenAI API
- **Architecture:** Full-stack with REST API communication

## � Project Structure

```
1-ai-chat/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── LLM.py               # OpenAI API integration
│   ├── requirements.txt      # Python dependencies
│   └── .env                 # Environment variables (not committed)
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main chat page
│   │   ├── layout.tsx       # Root layout
│   │   ├── service.ts       # API client service
│   │   ├── types.ts         # TypeScript type definitions
│   │   ├── globals.css      # Global styles
│   │   └── components/
│   │       └── chat.tsx     # Chat component
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── tailwind.config.js
└── README.md
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- Node.js 18 or higher
- OpenAI API key ([get one here](https://platform.openai.com/api-keys))

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create and activate a virtual environment:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the backend directory:
   ```env
   OPENAI_API_KEY=your_api_key_here
   ```

5. Start the FastAPI server:
   ```bash
   python main.py
   ```
   The backend will be available at `http://localhost:8000`
   API docs will be available at `http://localhost:8000/docs`

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the development server:
   ```bash
   npm run dev
   ```
   The frontend will be available at `http://localhost:3000`

4. Open your browser and start chatting!

---

## 🔄 API Endpoints

### POST `/query`

Send a message and receive an AI response.

**Request Body:**
```json
{
  "conversation": [
    {
      "role": "user",
      "content": "Your message here"
    }
  ]
}
```

**Response:**
```json
{
  "response": "AI's response to your message"
}
```

**Example cURL:**
```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"conversation": [{"role": "user", "content": "Hello, how are you?"}]}'
```

### GET `/docs`

Interactive API documentation powered by Swagger UI. Available at `http://localhost:8000/docs`

### GET `/openapi.json`

OpenAPI specification for the API endpoints.

---

## 📦 Dependencies

### Frontend Dependencies
- **Next.js** - React framework for production
- **React** - UI library
- **TypeScript** - Type-safe JavaScript
- **Tailwind CSS** - Utility-first CSS framework
- **ESLint** - Code quality and formatting

See `frontend/package.json` for the complete list.

### Backend Dependencies
- **FastAPI** - High-performance Python web framework
- **Pydantic** - Data validation using Python type hints
- **OpenAI** - Official OpenAI Python client library
- **python-dotenv** - Environment variable management
- **uvicorn** - ASGI web server

See `backend/requirements.txt` for the complete list.

## 🔐 Security Considerations

- **Never commit API keys** - Use `.env` files (add to `.gitignore`)
- **Use environment variables** - For all sensitive configuration
- **Validate inputs** - On both frontend and backend
- **Implement rate limiting** - For production deployments
- **Use HTTPS** - In production environments
- **Secure CORS** - Configure only for trusted origins

## 🚀 Deployment

### Frontend Deployment

**Build for production:**
```bash
cd frontend
npm run build
```

**Deploy to Vercel (recommended for Next.js):**
1. Push code to GitHub
2. Connect repository to Vercel
3. Deploy with automatic CI/CD

**Deploy to other platforms:**
- Netlify: Run `npm run build`, deploy the `.next` folder
- Self-hosted: Use `npm run build` and serve with Node.js or nginx

### Backend Deployment

**Using Docker:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
CMD ["python", "main.py"]
```

**Deploy to cloud platforms:**
- **Heroku** - Push with Git, set environment variables
- **Railway** - Connect GitHub repository
- **AWS** - Use EC2, ECS, or Lambda
- **Google Cloud** - Use Cloud Run or App Engine

**Environment variables needed:**
```
OPENAI_API_KEY=your_key_here
```

## 💡 Development Tips

- **Hot Reload** - Both frontend and backend support hot reloading during development
- **API Documentation** - Visit `http://localhost:8000/docs` to explore endpoints
- **TypeScript** - Use for better code quality and IDE support
- **Tailwind** - Use the utility classes for styling instead of custom CSS

## 🐛 Troubleshooting

**Backend not starting:**
- Ensure Python 3.8+ is installed
- Check that virtual environment is activated
- Verify `requirements.txt` is installed: `pip install -r requirements.txt`
- Check if port 8000 is available

**Frontend not connecting to backend:**
- Verify backend is running on `http://localhost:8000`
- Check CORS configuration in `main.py`
- Look at browser console for error messages

**OpenAI API errors:**
- Verify API key is correct in `.env` file
- Check account has API credits
- Review API rate limits

## 📚 Learn More

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
