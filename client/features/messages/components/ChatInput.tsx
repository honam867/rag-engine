"use client";

import { useState, useRef } from "react";
import { useSendMessage } from "../hooks/useMessages";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Loader2 } from "lucide-react";

export function ChatInput({ conversationId }: { conversationId: string }) {
  const { mutateAsync, isPending } = useSendMessage(conversationId);
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!content.trim() || isPending) return;
    
    const message = content.trim();
    setContent(""); // Optimistic clear
    
    try {
      await mutateAsync({ content: message });
    } catch (error) {
      // Restore content on error if needed, for now just log
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
    <form onSubmit={handleSubmit} className="relative rounded-lg border border-input bg-background p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring">
      <Textarea
        ref={textareaRef}
        className="min-h-[60px] w-full resize-none border-0 bg-transparent p-2 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
        rows={1}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Type a message..."
        disabled={isPending}
        style={{ height: 'auto', minHeight: '60px' }} // Simple auto-grow placeholder
      />
      <div className="flex items-center justify-between p-2">
         <span className="text-xs text-muted-foreground hidden sm:inline-block">
            Press Enter to send, Shift + Enter for new line
         </span>
         <Button 
            type="submit" 
            size="sm" 
            disabled={!content.trim() || isPending}
            className="gap-2"
         >
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send
         </Button>
      </div>
    </form>
  );
}
