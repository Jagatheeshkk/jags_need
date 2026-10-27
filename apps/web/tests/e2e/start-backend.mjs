// Starts a throwaway backend for end-to-end tests: fresh SQLite DB, migrations, seed, uvicorn.
// Uses only synthetic data and the mock connector; nothing is sent to any real portal.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apiDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../../services/api");
const venvPython =
  process.platform === "win32" ? path.join(apiDir, ".venv", "Scripts", "python.exe") : path.join(apiDir, ".venv", "bin", "python");
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");
const port = process.env.E2E_API_PORT ?? "8100";
const dbFile = path.join(apiDir, "e2e.db");

rmSync(dbFile, { force: true });
const env = {
  ...process.env,
  ENVIRONMENT: "test",
  DATABASE_URL: `sqlite:///${dbFile.replaceAll("\\", "/")}`,
  SECRET_KEY: "e2e-secret-key-not-for-production-0123456789",
  BOOTSTRAP_TOKEN: "",
};

for (const cmd of [["migrate"], ["seed"], ["seed-sample-jobs"]]) {
  const r = spawnSync(python, ["-m", "app.cli", ...cmd], { cwd: apiDir, env, stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status ?? 1);
}

const server = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port], {
  cwd: apiDir,
  env,
  stdio: "inherit",
});
const stop = () => server.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
server.on("exit", (code) => process.exit(code ?? 0));
