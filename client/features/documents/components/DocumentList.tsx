import { Document } from "../api/documents";
import { FileText, CheckCircle, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function DocumentList({ documents }: { documents: Document[] }) {
  if (!documents.length) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border border-dashed rounded-lg">
        <FileText className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      {documents.map((doc) => (
        <Card key={doc.id} className="shadow-none border hover:bg-muted/30 transition-colors">
          <CardContent className="p-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-8 w-8 flex items-center justify-center rounded bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400">
                <FileText className="h-4 w-4" />
              </div>
              <div>
                 <div className="text-sm font-medium truncate max-w-[200px] sm:max-w-md">{doc.title}</div>
              </div>
            </div>
            
            <div className={cn(
               "text-xs font-medium px-2 py-1 rounded-full flex items-center gap-1",
               doc.status === "completed" ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
            )}>
              {doc.status === "completed" ? <CheckCircle className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
              <span className="capitalize">{doc.status}</span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
