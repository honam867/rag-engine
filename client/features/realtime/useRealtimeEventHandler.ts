import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter, usePathname } from 'next/navigation';
import { toast } from 'sonner';
import { documentKeys, conversationKeys } from '@/lib/query-keys';

interface RealtimeEvent {
  type: string;
  payload: any;
}

export function useRealtimeEventHandler() {
  const queryClient = useQueryClient();
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();

  const handleEvent = useCallback(
    (event: RealtimeEvent) => {
      const { type, payload } = event;

      switch (type) {
        // --- DOCUMENTS ---
        case 'document.created': {
          const { workspace_id } = payload;
          // Invalidate list to fetch new doc
          queryClient.invalidateQueries({ queryKey: documentKeys.list(workspace_id) });
          toast.success(`Document uploaded: ${payload.document.title}`);
          break;
        }

        case 'document.status_updated': {
          const { workspace_id, document_id, status } = payload;
          // Optimistically update status in the list
          queryClient.setQueryData(documentKeys.list(workspace_id), (oldData: any) => {
            if (!oldData) return oldData;
            // Assuming oldData is an array or has .items
            // Adjust based on actual API response structure (likely { items: [] })
            const items = Array.isArray(oldData) ? oldData : oldData.items || [];
            
            const newItems = items.map((doc: any) => 
              doc.id === document_id ? { ...doc, status } : doc
            );

            return Array.isArray(oldData) ? newItems : { ...oldData, items: newItems };
          });

          // Notify user for important status changes
          if (status === 'ingested') {
             toast.success("Document ready to chat", {
                 description: "Processing complete."
             });
          } else if (status === 'error') {
             toast.error("Document processing failed");
          }
          break;
        }

        // --- MESSAGES ---
        case 'message.created':
        case 'message.status_updated': {
            const { conversation_id, message, workspace_id, status, content, metadata } = payload;
            
            // 1. Update Cache (for all cases)
            queryClient.setQueryData(conversationKeys.messages(conversation_id), (oldData: any) => {
                // Initialize as array. fetchMessages unwraps .items, so cache is Message[]
                const newItems = Array.isArray(oldData) ? [...oldData] : [];

                // Case A: Status Update (message already exists by ID)
                if (type === 'message.status_updated') {
                    const existingIndex = newItems.findIndex((m: any) => m.id === payload.message_id);
                    if (existingIndex > -1) {
                        const updatedMsg = { ...newItems[existingIndex], status };
                        if (content !== undefined) updatedMsg.content = content;
                        if (metadata !== undefined) updatedMsg.metadata = metadata;
                        newItems[existingIndex] = updatedMsg;
                    }
                    return newItems;
                }

                // Case B: Message Created (Check for duplication/optimistic replace)
                if (type === 'message.created') {
                    const incomingMsg = message;
                    
                    // 1. Check if ID already exists (idempotency)
                    const idExists = newItems.some((m: any) => m.id === incomingMsg.id);
                    if (idExists) {
                        return newItems; 
                    }

                    // 2. Try to find a matching Optimistic Message to replace
                    let replaced = false;
                    
                    if (incomingMsg.role === 'user') {
                        // Find user optimistic message with same content
                        const optIdx = newItems.findIndex((m: any) => m.isOptimistic && m.role === 'user' && m.content === incomingMsg.content);
                        if (optIdx > -1) {
                            newItems[optIdx] = incomingMsg; // Replace optimistic with real
                            replaced = true;
                        }
                    } else if (incomingMsg.role === 'ai') {
                        // Find AI optimistic message (usually pending/empty)
                        // We replace the *first* pending optimistic AI message we find
                        const optIdx = newItems.findIndex((m: any) => m.isOptimistic && m.role === 'ai');
                        if (optIdx > -1) {
                            newItems[optIdx] = incomingMsg; // Replace optimistic with real
                            replaced = true;
                        }
                    }

                    if (!replaced) {
                        newItems.push(incomingMsg);
                    }
                    
                    return newItems;
                }
                
                return newItems;
            });

            // 2. Notification Logic (Smart Toast)
            // Check if user is currently viewing this conversation
            // URL pattern usually: /workspaces/[wsId]/conversations/[convId]
            const currentConvId = params?.conversationId; // Ensure your dynamic route param is named 'conversationId'
            
            // If we are NOT in the conversation, show a toast
            if (currentConvId !== conversation_id) {
                // Only notify for AI messages or specific statuses to avoid double notification for self
                // Assuming message.role or we infer from type. 
                // Usually we only care if AI replied.
                const isAiReply = message?.role === 'ai' || (type === 'message.status_updated' && status === 'done');
                
                if (isAiReply) {
                    toast.info("AI replied in another conversation", {
                        description: message?.content ? (message.content.substring(0, 50) + "...") : "Click to view",
                        action: {
                            label: "View",
                            onClick: () => router.push(`/workspaces/${workspace_id}/conversations/${conversation_id}`)
                        }
                    });
                }
            }
            break;
        }

        // --- JOBS ---
        case 'job.status_updated': {
            // Can be used to show global progress bar or detailed job status
            // For now, logging is enough or specific UI components can subscribe via query cache if we stored jobs there.
            break;
        }
      }
    },
    [queryClient, params, router, pathname]
  );

  return { handleEvent };
}
