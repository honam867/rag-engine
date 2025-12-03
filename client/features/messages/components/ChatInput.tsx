"use client";

import { useState, useRef, useEffect } from "react";
import { useSendMessage } from "../hooks/useMessages";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function ChatInput({ conversationId }: { conversationId: string }) {
  const { mutateAsync, isPending } = useSendMessage(conversationId);
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [content]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!content.trim() || isPending) return;
    
    const message = content.trim();
    setContent(""); // Optimistic clear
    if (textareaRef.current) textareaRef.current.style.height = 'auto'; // Reset height
    
    try {
      await mutateAsync({ content: message });
    } catch (error) {
      console.error(error);
      setContent(message);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="relative">
        <form 
            onSubmit={handleSubmit} 
            className="relative flex items-end gap-2 p-2 bg-background border rounded-xl shadow-sm ring-offset-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2"
        >
            <Textarea
                ref={textareaRef}
                className="min-h-[48px] w-full resize-none border-0 bg-transparent p-4 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 text-base max-h-[200px] leading-relaxed pr-12"
                rows={1}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message RAG Engine..."
                disabled={isPending}
            />
            <Button 
                type="submit" 
                size="icon" 
                disabled={!content.trim() || isPending}
                className={cn(
                    "absolute bottom-2 right-2 h-8 w-8 shrink-0 rounded-lg transition-all", 
                    content.trim() ? "opacity-100" : "opacity-50"
                )}
            >
                {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                <span className="sr-only">Send</span>
            </Button>
        </form>
        <div className="text-center mt-2">
             <span className="text-[10px] text-muted-foreground">
                AI can make mistakes. Please verify important information.
             </span>
        </div>
    </div>
  );
}