// frontend/src/lib/mockData.ts
import { ChatMessage } from "@/types/chat";

export const mockMessages: ChatMessage[] = [
  {
    id: "msg-1",
    role: "user",
    content: "What are the top stock picks right now?",
    timestamp: new Date("2026-03-31T09:00:00"),
    parentId: null,
    children: ["msg-2"],
    editHistory: ["What are the top stock picks right now?"],
    currentEditIndex: 0,
  },
  {
    id: "msg-2",
    role: "assistant",
    content:
      "Based on current market conditions, here are my top algorithmic setups for today:\n\n1. NVDA — strong AI infrastructure spending momentum\n2. TSLA — EV market recovery and robotaxi catalysts\n3. AAPL — services revenue growth with new product cycle\n\nWould you like me to dive deeper into any of these?",
    timestamp: new Date("2026-03-31T09:00:15"),
    parentId: "msg-1",
    children: ["msg-3"],
  },
  {
    id: "msg-3",
    role: "user",
    content: "Tell me more about NVDA",
    timestamp: new Date("2026-03-31T09:02:00"),
    parentId: "msg-2",
    children: ["msg-4", "msg-5"],
    editHistory: ["Tell me about NVDA", "Tell me more about NVDA"],
    currentEditIndex: 1,
  },
  {
    id: "msg-4",
    role: "assistant",
    content:
      "NVIDIA (NVDA) shows strong momentum. The recent earnings beat driven by AI datacenter demand makes this a compelling long setup.",
    timestamp: new Date("2026-03-31T09:02:10"),
    parentId: "msg-3",
    children: [],
  },
  {
    id: "msg-5",
    role: "assistant",
    content:
      "Here's the deeper technical analysis for NVDA. The chart shows a classic ascending triangle pattern with resistance at $920.",
    timestamp: new Date("2026-03-31T09:02:30"),
    parentId: "msg-3",
    children: [],
  },
  {
    id: "msg-6",
    role: "user",
    content: "Can you show me the chart for TSLA?",
    timestamp: new Date("2026-03-31T09:05:00"),
    parentId: "msg-4",
    children: ["msg-7"],
    editHistory: ["Can you show me the chart for TSLA?"],
    currentEditIndex: 0,
  },
  {
    id: "msg-7",
    role: "assistant",
    content:
      "Here is the candlestick chart for Tesla (TSLA) over the last 30 days. You can see the volatility around earnings, with a breakout above the 50-day MA.",
    timestamp: new Date("2026-03-31T09:05:15"),
    parentId: "msg-6",
    children: [],
  },
];
