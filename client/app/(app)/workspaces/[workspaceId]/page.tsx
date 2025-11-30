"use client";

import { DocumentList } from "@/features/documents/components/DocumentList";
import { UploadDocumentsForm } from "@/features/documents/components/UploadDocumentsForm";
import { useWorkspaceDocuments } from "@/features/documents/hooks/useDocuments";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ROUTES } from "@/lib/routes";

export default function WorkspaceDetailPage() {
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const { data, isLoading, isError } = useWorkspaceDocuments(workspaceId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Workspace</h1>
          <p className="text-sm text-gray-600">ID: {workspaceId}</p>
        </div>
        <Link
          className="text-sm font-medium text-blue-600 hover:underline"
          href={ROUTES.workspaceConversations(workspaceId)}
        >
          Conversations →
        </Link>
      </div>

      <UploadDocumentsForm workspaceId={workspaceId} />

      <div className="rounded-md border border-dashed border-border p-4">
        {isLoading && <p className="text-sm text-gray-600">Loading documents...</p>}
        {isError && <p className="text-sm text-red-600">Failed to load documents.</p>}
        {data ? <DocumentList documents={data} /> : null}
      </div>
    </div>
  );
}
