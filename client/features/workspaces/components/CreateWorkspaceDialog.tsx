"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useRouter } from "next/navigation";
import { FolderPlus } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCreateWorkspace } from "../hooks/useWorkspaces";

const formSchema = z.object({
  name: z.string().min(1, "Workspace name is required"),
  description: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

export function CreateWorkspaceDialog({ children }: { children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const createMutation = useCreateWorkspace();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      description: "",
    },
  });

  const onSubmit = async (data: FormValues) => {
    try {
      const newWorkspace = await createMutation.mutateAsync({
        name: data.name,
        description: data.description || null,
      });
      
      setOpen(false);
      reset();
      
      // Navigate to the new workspace immediately
      if (newWorkspace?.id) {
        router.push(`/workspaces/${newWorkspace.id}`);
      }
    } catch (error) {
      console.error("Failed to create workspace:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {children || (
          <Button variant="outline" size="icon">
            <FolderPlus className="h-4 w-4" />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Create New Workspace</DialogTitle>
          <DialogDescription>
            Create a dedicated space for your documents and conversations.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="name" className="text-sm font-medium leading-none">
              Name
            </label>
            <Input
              id="name"
              placeholder="My Awesome Project"
              {...register("name")}
              disabled={isSubmitting}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>
          <div className="space-y-2">
            <label htmlFor="description" className="text-sm font-medium leading-none">
              Description (Optional)
            </label>
            <Textarea
              id="description"
              placeholder="What is this workspace for?"
              {...register("description")}
              disabled={isSubmitting}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating..." : "Create Workspace"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
