import { demoResponse } from "@/lib/demo";

// Browser calls in demo mode land here instead of the FastAPI proxy (see send() in lib/api.ts).
async function handle(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const { search } = new URL(req.url);
  try {
    return Response.json(demoResponse(req.method, `/${path.join("/")}${search}`));
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 403 });
  }
}

export { handle as GET, handle as POST, handle as PATCH, handle as DELETE };
