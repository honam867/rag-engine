import { ROUTES } from "@/lib/routes";
import Link from "next/link";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen w-full flex-col items-center justify-center bg-background px-4">
      <div className="w-full max-w-md space-y-4">
        <LoginForm />
        
        <div className="text-center">
          <Button variant="link" asChild className="text-muted-foreground">
            <Link href={ROUTES.workspaces}>
              Skip to app (Development only)
            </Link>
          </Button>
        </div>
      </div>
    </main>
  );
}
