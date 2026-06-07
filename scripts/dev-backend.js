// Cross-platform launcher for the backend dev server.
// Picks the correct venv Python path for the current OS.
const { spawn } = require("child_process");
const path = require("path");

const isWindows = process.platform === "win32";
const python = isWindows
  ? path.join(".venv", "Scripts", "python.exe")
  : path.join(".venv", "bin", "python");

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
  { cwd: path.join(__dirname, "..", "backend"), stdio: "inherit" }
);

child.on("exit", (code) => process.exit(code ?? 0));
