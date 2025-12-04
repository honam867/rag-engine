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
      console.log('[Realtime] Event received:', event.type, event.payload);
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
            const { conversation_id, message, workspace_id, status } = payload;
            
            // 1. Update Cache (for all cases)
            queryClient.setQueryData(conversationKeys.messages(conversation_id), (oldData: any) => {
                if (!oldData) return oldData;
                const items = Array.isArray(oldData) ? oldData : oldData.items || [];
                
                // If message already exists (e.g. optimistic update or status update), update it
                const existingIndex = items.findIndex((m: any) => m.id === message?.id || m.id === payload.message_id);
                
                if (existingIndex > -1) {
                    const newItems = [...items];
                    // If it's a status update, payload might just have message_id and status
                    if (type === 'message.status_updated') {
                        newItems[existingIndex] = { ...newItems[existingIndex], status };
                         // If content is provided in payload (Phase 5 backend might support streaming later)
                         if (payload.content) {
                             newItems[existingIndex].content = payload.content;
                         }
                    } else {
                        // Full message replace
                        newItems[existingIndex] = message;
                    }
                    return Array.isArray(oldData) ? newItems : { ...oldData, items: newItems };
                } else if (type === 'message.created') {
                    // New message -> Append
                    const newItems = [...items, message];
                    return Array.isArray(oldData) ? newItems : { ...oldData, items: newItems };
                }
                
                return oldData;
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
