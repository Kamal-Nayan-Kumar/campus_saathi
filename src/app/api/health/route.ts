export async function GET() {
  return Response.json({ status: "healthy" });
}

export async function HEAD() {
  return new Response(null, { status: 200 });
}
