import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, resolve } from "node:path";

const root = resolve(process.argv[2] ?? "dist_electron");
const port = Number(
  process.env.PORT ?? process.env.OUTLAYS_DESKTOP_UPDATE_FEED_PORT ?? process.env.OUTLAYS_DESKTOP_UPDATE_FEED_PORT ?? 47821
);

if (!existsSync(root) || !statSync(root).isDirectory()) {
  console.error(`Update feed directory does not exist: ${root}`);
  process.exit(1);
}

const contentTypes = {
  ".yml": "text/yaml",
  ".yaml": "text/yaml",
  ".json": "application/json",
  ".zip": "application/zip",
  ".dmg": "application/octet-stream",
  ".exe": "application/vnd.microsoft.portable-executable"
};

const server = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  const requestedPath = resolve(join(root, decodeURIComponent(url.pathname)));
  if (!requestedPath.startsWith(root)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }
  if (!existsSync(requestedPath) || !statSync(requestedPath).isFile()) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }
  response.writeHead(200, {
    "Content-Type": contentTypes[extname(requestedPath)] ?? "application/octet-stream"
  });
  createReadStream(requestedPath).pipe(response);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving local update feed from ${root}`);
  console.log(`OUTLAYS_DESKTOP_UPDATE_BASE_URL=http://127.0.0.1:${port}`);
});
