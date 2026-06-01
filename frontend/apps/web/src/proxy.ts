import { NextResponse, type NextRequest } from "next/server";
import { verifySession } from "@/lib/auth/jwt";
import { SESSION_COOKIE } from "@/lib/constants";

// "/" is the public marketing landing page; everything else under (app) is gated.
const PUBLIC_PATHS = ["/", "/login"];

// Next.js 16 "proxy" convention (formerly middleware). Edge runtime —
// only does stateless JWT verification, never touches DB/Redis.
export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const session = await verifySession(token);
  const isPublic = PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );

  if (!session && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (session && pathname === "/login") {
    const url = req.nextUrl.clone();
    url.pathname = "/workspace";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Run on everything except auth API, the large-body upload proxy, next
  // internals, and static files. `api/upload` is excluded so big videos stream
  // straight through the rewrite to the backend — the middleware body-clone
  // caps bodies (default 10MB) and breaks large uploads ("上传失败").
  matcher: ["/((?!api/auth|api/upload|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
