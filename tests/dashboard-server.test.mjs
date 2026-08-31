import assert from "node:assert/strict";
import { chmod, mkdtemp, mkdir, readFile, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterEach, describe, test } from "node:test";
import { spawnSync } from "node:child_process";
import {
  DashboardError,
  browserLaunchCommand,
  createDashboardServer,
  listWorkspaceCandidates,
  listWorkspaceDirectory,
  pathsReferToSameFile,
  resolveWorkspaceDirectory,
  resolveWorkspacePath,
  runCandidateAction,
  scanWorkspace,
  searchWorkspace,
} from "../skills/story/scripts/dashboard-server.mjs";

const temporaryDirectories = [];
const runningServers = [];

afterEach(async () => {
  await Promise.all(
    runningServers.splice(0).map(
      (server) => new Promise((accept) => server.close(accept)),
    ),
  );
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

async function createCandidateWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-candidates-"));
  temporaryDirectories.push(root);
  const book = resolve(root, "长篇", "候选书");
  await mkdir(resolve(book, "正文"), { recursive: true });
  await mkdir(resolve(book, "大纲"), { recursive: true });
  await mkdir(resolve(book, "骨架"), { recursive: true });
  await mkdir(resolve(book, "追踪"), { recursive: true });
  await mkdir(resolve(book, "候选", "_历史"), { recursive: true });
  await writeFile(resolve(book, "正文", "第001章_旧稿.md"), "# 第001章 旧稿\n正文。\n", "utf8");
  await writeFile(resolve(book, "大纲", "细纲_第002章.md"), "# 细纲\n", "utf8");
  await writeFile(resolve(book, "骨架", "第002章_骨架.md"), "# 骨架\n", "utf8");
  await writeFile(resolve(book, "候选", "第002章_新章.md"), "# 第002章 新章\n候选正文。\n", "utf8");
  await writeFile(
    resolve(book, "候选", "第002章_追踪事务.json"),
    JSON.stringify({ expected_state_revision: 7, candidate_binding: { schema_version: 1 } }),
    "utf8",
  );
  await writeFile(resolve(book, "候选", "第003章_无事务.md"), "# 第003章\n候选正文。\n", "utf8");
  await writeFile(resolve(book, "追踪", "上下文.md"), "受管理状态", "utf8");
  return { root, book };
}

describe("candidate review", () => {
  test("lists candidates through the transaction authority with version and state binding", async () => {
    const { root } = await createCandidateWorkspace();
    const listing = await listWorkspaceCandidates(root);
    assert.equal(listing.total, 2);
    const [second, third] = listing.projects[0].candidates;
    assert.equal(second.chapter, 2);
    assert.match(second.candidateVersion, /^[a-f0-9]{64}$/);
    assert.equal(second.hasTransaction, true);
    assert.equal(second.hasBinding, true);
    assert.equal(second.expectedStateRevision, 7);
    assert.equal(second.outlinePath, "长篇/候选书/大纲/细纲_第002章.md");
    assert.equal(second.skeletonPath, "长篇/候选书/骨架/第002章_骨架.md");
    assert.equal(second.previousFinalPath, "长篇/候选书/正文/第001章_旧稿.md");
    assert.equal(third.hasTransaction, false);
  });

  test("rejects stale actions and archives an unchanged candidate", async () => {
    const { root, book } = await createCandidateWorkspace();
    const listing = await listWorkspaceCandidates(root);
    const third = listing.projects[0].candidates.find((entry) => entry.chapter === 3);
    await writeFile(resolve(book, "候选", third.name), "已被外部改写", "utf8");
    await assert.rejects(
      runCandidateAction(root, {
        action: "reject",
        project: "长篇/候选书",
        chapter: 3,
        candidateVersion: third.candidateVersion,
      }),
      (error) => error instanceof DashboardError && error.code === "candidate_changed",
    );
    const refreshed = await listWorkspaceCandidates(root);
    const current = refreshed.projects[0].candidates.find((entry) => entry.chapter === 3);
    const result = await runCandidateAction(root, {
      action: "reject",
      project: "长篇/候选书",
      chapter: 3,
      candidateVersion: current.candidateVersion,
    });
    assert.equal(result.ok, true);
    await assert.rejects(stat(resolve(book, "候选", third.name)));
  });

  test("blocks generic edits to tracking state and candidate transaction files", async () => {
    const { root } = await createCandidateWorkspace();
    const baseUrl = await startServer(root);
    for (const path of ["长篇/候选书/追踪/上下文.md", "长篇/候选书/候选/第002章_追踪事务.json"]) {
      const loaded = await fetch(`${baseUrl}/api/file?path=${encodeURIComponent(path)}`).then((response) => response.json());
      const response = await fetch(`${baseUrl}/api/file`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, content: "旁路修改", expectedVersion: loaded.version }),
      });
      assert.equal(response.status, 403);
      assert.equal((await response.json()).error.code, "managed_state_read_only");
    }
  });
});

async function createWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-test-"));
  temporaryDirectories.push(root);
  await mkdir(resolve(root, "拆文库", "盘龙", "章节"), { recursive: true });
  await mkdir(resolve(root, "长篇", "示例书", "大纲"), { recursive: true });
  await mkdir(resolve(root, "长篇", "示例书", "正文"), { recursive: true });
  // 基建目录必须落在被扫描的库/项目内部：放在工作区根下永远进不了树，
  // 断言就成了空转，测不出忽略规则有没有失效。
  await mkdir(resolve(root, "长篇", "示例书", ".git", "objects"), { recursive: true });
  await mkdir(resolve(root, "长篇", "示例书", "正文", "node_modules", "fake-package"), {
    recursive: true,
  });
  await mkdir(resolve(root, "拆文库", "盘龙", ".omc", "state"), { recursive: true });
  await writeFile(resolve(root, "拆文库", "盘龙", "拆文报告.md"), "# 盘龙\n", "utf8");
  await writeFile(resolve(root, "拆文库", "盘龙", "章节", "第1章.md"), "第一章", "utf8");
  await writeFile(resolve(root, "长篇", "示例书", "大纲", "总纲.md"), "# 总纲\n", "utf8");
  await writeFile(resolve(root, "长篇", "示例书", "正文", "第001章.md"), "初稿", "utf8");
  await writeFile(resolve(root, "长篇", "示例书", ".git", "config"), "secret", "utf8");
  await writeFile(
    resolve(root, "长篇", "示例书", "正文", "node_modules", "fake-package", "index.js"),
    "x",
    "utf8",
  );
  await writeFile(resolve(root, "拆文库", "盘龙", ".omc", "state", "secrets.json"), "{}", "utf8");
  await writeFile(resolve(root, "长篇", "示例书", "封面.png"), "not-an-image", "utf8");
  return root;
}

async function createProjectDiscoveryWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-projects-"));
  temporaryDirectories.push(root);

  await mkdir(resolve(root, "长篇", "标准长篇", "正文"), { recursive: true });
  await mkdir(resolve(root, "短篇", "标准短篇"), { recursive: true });
  await writeFile(resolve(root, "短篇", "标准短篇", "正文.md"), "正文", "utf8");
  await writeFile(resolve(root, "短篇", "标准短篇", "小节大纲.md"), "大纲", "utf8");
  await writeFile(resolve(root, "短篇", "标准短篇", "设定.md"), "设定", "utf8");

  await mkdir(resolve(root, "普通资料"), { recursive: true });
  await writeFile(resolve(root, "普通资料", "正文.md"), "不是短篇工程", "utf8");

  await mkdir(resolve(root, "拆文库", "伪项目"), { recursive: true });
  await writeFile(resolve(root, "拆文库", "伪项目", "正文.md"), "拆文原文", "utf8");
  await writeFile(resolve(root, "拆文库", "伪项目", "设定.md"), "拆文资料", "utf8");

  return root;
}

// 一个目录超过单页 200 项即可验证分页；不用再造 5000 个文件测试全量树预算。
async function createOversizedWorkspace(fileCount = 205) {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-oversized-"));
  temporaryDirectories.push(root);
  const body = resolve(root, "长篇", "巨书", "正文");
  const library = resolve(root, "拆文库", "盘龙");
  await mkdir(resolve(root, "长篇", "巨书", "大纲"), { recursive: true });
  await mkdir(body, { recursive: true });
  await mkdir(resolve(library, "章节"), { recursive: true });
  await writeFile(resolve(library, "拆文报告.md"), "# 盘龙\n", "utf8");
  for (let start = 0; start < fileCount; start += 200) {
    await Promise.all(
      Array.from({ length: Math.min(200, fileCount - start) }, (_, offset) =>
        writeFile(
          resolve(body, `第${String(start + offset + 1).padStart(5, "0")}章.md`),
          "初稿",
          "utf8",
        ),
      ),
    );
  }
  return root;
}

async function createDeepSearchWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-deep-search-"));
  temporaryDirectories.push(root);
  const deepRoot = resolve(root, "A深项目", "正文");
  const targetRoot = resolve(root, "B目标项目", "正文");
  await mkdir(
    resolve(deepRoot, ...Array.from({ length: 25 }, (_, index) => `第${index + 1}层`)),
    { recursive: true },
  );
  await mkdir(targetRoot, { recursive: true });
  await writeFile(resolve(targetRoot, "第001章.md"), "目标正文", "utf8");
  return root;
}

async function createSearchBudgetWorkspace(fileCount = 5005) {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-search-budget-"));
  temporaryDirectories.push(root);
  const body = resolve(root, "预算项目", "正文");
  await mkdir(body, { recursive: true });
  for (let start = 0; start < fileCount; start += 250) {
    await Promise.all(
      Array.from({ length: Math.min(250, fileCount - start) }, (_, offset) =>
        writeFile(
          resolve(body, `普通文件_${String(start + offset + 1).padStart(5, "0")}.md`),
          "正文",
          "utf8",
        ),
      ),
    );
  }
  return root;
}

async function startServer(root) {
  const server = createDashboardServer({ root });
  await new Promise((accept, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", accept);
  });
  runningServers.push(server);
  const { port } = server.address();
  return `http://127.0.0.1:${port}`;
}

describe("workspace scanning", () => {
  test("recognizes standard long and short projects without treating loose files or libraries as projects", async () => {
    const root = await createProjectDiscoveryWorkspace();
    const workspace = await scanWorkspace(root);

    assert.deepEqual(
      workspace.projects.map((entry) => entry.path),
      ["短篇/标准短篇", "长篇/标准长篇"],
    );
    assert.deepEqual(workspace.libraries.map((entry) => entry.path), ["拆文库/伪项目"]);
    assert.ok(!workspace.projects.some((entry) => entry.path === "普通资料"));
    assert.ok(!workspace.projects.some((entry) => entry.path.startsWith("拆文库/")));
  });

  test("does not use symlinked short-story marker files", async (context) => {
    const root = await createProjectDiscoveryWorkspace();
    const candidate = resolve(root, "短篇", "符号链接标记");
    await mkdir(candidate, { recursive: true });
    await writeFile(resolve(candidate, "设定.md"), "设定", "utf8");
    try {
      await symlink(resolve(root, "短篇", "标准短篇", "正文.md"), resolve(candidate, "正文.md"));
    } catch (error) {
      if (error?.code === "EPERM") {
        context.skip("当前平台不允许创建测试符号链接");
        return;
      }
      throw error;
    }

    const workspace = await scanWorkspace(root);
    assert.ok(!workspace.projects.some((entry) => entry.path === "短篇/符号链接标记"));
  });

  test("uses a stable dot path when the workspace itself is a short-story project", async () => {
    const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-root-project-"));
    temporaryDirectories.push(root);
    await writeFile(resolve(root, "正文.md"), "正文", "utf8");
    await writeFile(resolve(root, "小节大纲.md"), "大纲", "utf8");
    await writeFile(resolve(root, "设定.md"), "设定", "utf8");

    const workspace = await scanWorkspace(root);
    assert.deepEqual(workspace.projects.map((entry) => entry.path), ["."]);
    const page = await listWorkspaceDirectory(root, ".");
    assert.equal(page.path, ".");
    assert.deepEqual(
      page.entries.map((entry) => entry.name),
      ["设定.md", "小节大纲.md", "正文.md"],
    );
  });

  test("discovers roots without recursively serializing every manuscript", async () => {
    const workspace = await scanWorkspace(resolve("demo"));
    assert.deepEqual(
      workspace.libraries.map((entry) => entry.path),
      ["拆文库/曾将爱意私藏", "拆文库/盘龙"],
    );
    assert.deepEqual(
      workspace.projects.map((entry) => entry.path),
      ["长篇/让你管账号，你高燃混剪炸全网"],
    );
    assert.equal(workspace.stats.libraries, 2);
    assert.equal(workspace.stats.projects, 1);
    assert.equal(workspace.stats.editableFiles, null);
    assert.equal(workspace.stats.onDemand, true);
    assert.ok(workspace.libraries.every((entry) => entry.loaded === false));
    assert.ok(workspace.projects.every((entry) => entry.children.length === 0));
    assert.doesNotMatch(JSON.stringify(workspace), /第020章_老兵的礼物/);
    assert.equal(workspace.limits.truncated, false);
    assert.equal(workspace.limits.directoryPageSize, 200);
  });

  test("loads only one directory level and keeps infrastructure folders hidden", async () => {
    const root = await createWorkspace();
    const page = await listWorkspaceDirectory(root, "长篇/示例书");
    assert.doesNotMatch(JSON.stringify(page), /\.git/);
    assert.doesNotMatch(JSON.stringify(page), /第001章\.md/);
    assert.deepEqual(
      page.entries.filter((entry) => entry.type === "directory").map((entry) => entry.name),
      ["大纲", "正文"],
    );
    const cover = page.entries.find((entry) => entry.name === "封面.png");
    assert.equal(cover.editable, false);
    assert.equal(page.nextCursor, null);

    const bodyPage = await listWorkspaceDirectory(root, "长篇/示例书/正文");
    assert.deepEqual(bodyPage.entries.map((entry) => entry.name), ["第001章.md"]);
    assert.doesNotMatch(JSON.stringify(bodyPage), /node_modules|fake-package/);

    const libraryPage = await listWorkspaceDirectory(root, "拆文库/盘龙");
    assert.deepEqual(
      libraryPage.entries.map((entry) => entry.name),
      ["章节", "拆文报告.md"],
    );
    assert.doesNotMatch(JSON.stringify(libraryPage), /\.omc|secrets\.json/);
  });

  test("paginates a wide directory without dropping or duplicating files", async () => {
    const root = await createOversizedWorkspace();
    const path = "长篇/巨书/正文";
    const first = await listWorkspaceDirectory(root, path);
    const second = await listWorkspaceDirectory(root, path, first.nextCursor);
    assert.equal(first.entries.length, 200);
    assert.equal(first.nextCursor, "200");
    assert.equal(second.entries.length, 5);
    assert.equal(second.nextCursor, null);
    assert.equal(new Set([...first.entries, ...second.entries].map((entry) => entry.path)).size, 205);
  });

  test("searches unloaded descendants on demand and respects the active collection", async () => {
    const root = await createWorkspace();
    const projects = await searchWorkspace(root, "第001章", "projects");
    assert.deepEqual(projects.results.map((entry) => entry.path), [
      "长篇/示例书/正文/第001章.md",
    ]);
    const libraries = await searchWorkspace(root, "第1章", "libraries");
    assert.deepEqual(libraries.results.map((entry) => entry.path), [
      "拆文库/盘龙/章节/第1章.md",
    ]);
    assert.equal(projects.truncated, false);
    const pathOnly = await searchWorkspace(root, "示例书", "projects");
    assert.deepEqual(pathOnly.results, []);
  });

  test("continues searching later projects after one subtree exceeds the depth limit", async () => {
    const root = await createDeepSearchWorkspace();
    const result = await searchWorkspace(root, "第001章", "projects");
    assert.deepEqual(result.results.map((entry) => entry.path), [
      "B目标项目/正文/第001章.md",
    ]);
    assert.equal(result.truncated, true);
    assert.deepEqual(result.truncation, {
      byResults: false,
      byNodes: false,
      byDepth: true,
      byReadError: false,
    });
  });

  test("reports result-limit and node-budget truncation independently", async () => {
    const resultRoot = await createOversizedWorkspace(205);
    const byResults = await searchWorkspace(resultRoot, "第", "projects");
    assert.equal(byResults.results.length, 100);
    assert.deepEqual(byResults.truncation, {
      byResults: true,
      byNodes: false,
      byDepth: false,
      byReadError: false,
    });

    const budgetRoot = await createSearchBudgetWorkspace();
    const byNodes = await searchWorkspace(budgetRoot, "不存在的文件名", "projects");
    assert.deepEqual(byNodes.results, []);
    assert.deepEqual(byNodes.truncation, {
      byResults: false,
      byNodes: true,
      byDepth: false,
      byReadError: false,
    });
  });

  test("marks search results incomplete when an unloaded descendant is unreadable", async (context) => {
    if (process.platform === "win32" || process.getuid?.() === 0) {
      context.skip("当前平台或用户无法制造不可读目录");
      return;
    }
    const root = await createWorkspace();
    const restricted = resolve(root, "长篇", "示例书", "正文", "受限卷");
    await mkdir(restricted, { recursive: true });
    await writeFile(resolve(restricted, "目标章.md"), "不可读取的正文", "utf8");
    await chmod(restricted, 0o000);
    try {
      const baseUrl = await startServer(root);
      const response = await fetch(
        `${baseUrl}/api/search?q=${encodeURIComponent("目标章")}&scope=projects`,
      );
      assert.equal(response.status, 200);
      const result = await response.json();
      assert.deepEqual(result.results, []);
      assert.equal(result.truncated, true);
      assert.deepEqual(result.truncation, {
        byResults: false,
        byNodes: false,
        byDepth: false,
        byReadError: true,
      });
      assert.deepEqual(
        result.scanErrors.map(({ path, code }) => ({ path, code })),
        [{ path: "长篇/示例书/正文/受限卷", code: "EACCES" }],
      );
    } finally {
      await chmod(restricted, 0o755);
    }
  });
});

describe("path boundary", () => {
  test("rejects traversal and absolute paths", async () => {
    const root = await createWorkspace();
    await assert.rejects(
      resolveWorkspacePath(root, "../outside.md"),
      (error) => error instanceof DashboardError && error.code === "path_outside_workspace",
    );
    await assert.rejects(
      resolveWorkspacePath(root, "/etc/hosts"),
      (error) => error instanceof DashboardError && error.code === "path_outside_workspace",
    );
    await assert.rejects(
      resolveWorkspaceDirectory(root, "../outside"),
      (error) => error instanceof DashboardError && error.code === "path_outside_workspace",
    );
  });

  test("does not follow file symlinks", async (context) => {
    const root = await createWorkspace();
    const outside = resolve(root, "..", `outside-${Date.now()}.md`);
    await writeFile(outside, "outside", "utf8");
    temporaryDirectories.push(outside);
    try {
      await symlink(outside, resolve(root, "逃逸.md"));
    } catch (error) {
      if (error?.code === "EPERM") {
        context.skip("当前平台不允许创建测试符号链接");
        return;
      }
      throw error;
    }
    await assert.rejects(
      resolveWorkspacePath(root, "逃逸.md", { editableOnly: true }),
      (error) => error instanceof DashboardError && error.code === "symlink_not_editable",
    );
  });
});

describe("CLI portability", () => {
  test("uses each operating system's default-browser command", () => {
    const url = "http://127.0.0.1:43110";
    assert.deepEqual(browserLaunchCommand(url, "darwin"), {
      command: "open",
      args: [url],
    });
    assert.deepEqual(browserLaunchCommand(url, "linux"), {
      command: "xdg-open",
      args: [url],
    });
    assert.deepEqual(browserLaunchCommand(url, "win32"), {
      command: "cmd",
      args: ["/c", "start", "", url],
    });
  });

  test("recognizes the CLI entrypoint through a symlinked install path", async (context) => {
    const root = await createWorkspace();
    const alias = `${root}-alias`;
    temporaryDirectories.push(alias);
    try {
      await symlink(root, alias, process.platform === "win32" ? "junction" : "dir");
    } catch (error) {
      if (error?.code === "EPERM") {
        context.skip("当前平台不允许创建测试目录链接");
        return;
      }
      throw error;
    }

    assert.equal(
      pathsReferToSameFile(
        resolve(root, "长篇", "示例书", "正文", "第001章.md"),
        resolve(alias, "长篇", "示例书", "正文", "第001章.md"),
      ),
      true,
    );
  });
});

describe("HTTP API", () => {
  test("handles the browser favicon request without a console-visible 404", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);

    const response = await fetch(`${baseUrl}/favicon.ico`);
    assert.equal(response.status, 204);
    assert.equal(await response.text(), "");
  });

  test("serves lazy roots, directory pages, and on-demand search", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);

    const workspace = await fetch(`${baseUrl}/api/workspace`).then((response) => response.json());
    assert.deepEqual(workspace.projects[0].children, []);
    assert.doesNotMatch(JSON.stringify(workspace), /第001章\.md/);

    const tree = await fetch(
      `${baseUrl}/api/tree?path=${encodeURIComponent("长篇/示例书")}`,
    ).then((response) => response.json());
    assert.deepEqual(
      tree.entries.filter((entry) => entry.type === "directory").map((entry) => entry.name),
      ["大纲", "正文"],
    );

    const search = await fetch(
      `${baseUrl}/api/search?q=${encodeURIComponent("第001章")}&scope=projects`,
    ).then((response) => response.json());
    assert.deepEqual(search.results.map((entry) => entry.path), [
      "长篇/示例书/正文/第001章.md",
    ]);

    const traversal = await fetch(
      `${baseUrl}/api/tree?path=${encodeURIComponent("../outside")}`,
    );
    assert.equal(traversal.status, 403);
    const invalidCursor = await fetch(
      `${baseUrl}/api/tree?path=${encodeURIComponent("长篇/示例书")}&cursor=next`,
    );
    assert.equal(invalidCursor.status, 400);
    const hiddenDirectory = await fetch(
      `${baseUrl}/api/tree?path=${encodeURIComponent("长篇/示例书/.git")}`,
    );
    assert.equal(hiddenDirectory.status, 403);
  });

  test("escapes HTML-significant characters in JSON responses", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const query = "<script>alert(1)</script>&\u2028\u2029";

    const response = await fetch(
      `${baseUrl}/api/search?q=${encodeURIComponent(query)}&scope=projects`,
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("content-type"), "application/json; charset=utf-8");

    const rawBody = await response.text();
    assert.doesNotMatch(rawBody, /[<>&\u2028\u2029]/u);
    assert.equal(JSON.parse(rawBody).query, query.trim());
  });

  test("loads and atomically saves an editable file", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";

    const loadedResponse = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    );
    assert.equal(loadedResponse.status, 200);
    assert.match(loadedResponse.headers.get("content-security-policy"), /default-src 'self'/);
    const loaded = await loadedResponse.json();
    assert.equal(loaded.content, "初稿");

    const savedResponse = await fetch(`${baseUrl}/api/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: filePath,
        content: "修改后的正文",
        expectedVersion: loaded.version,
      }),
    });
    assert.equal(savedResponse.status, 200);
    const saved = await savedResponse.json();
    assert.equal(saved.ok, true);
    assert.equal(await readFile(resolve(root, filePath), "utf8"), "修改后的正文");
  });

  test("returns 409 instead of overwriting an externally changed file", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const loaded = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    ).then((response) => response.json());

    await new Promise((accept) => setTimeout(accept, 20));
    await writeFile(resolve(root, filePath), "外部程序的新内容", "utf8");

    const response = await fetch(`${baseUrl}/api/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: filePath,
        content: "Dashboard 里的旧内容",
        expectedVersion: loaded.version,
      }),
    });
    assert.equal(response.status, 409);
    const payload = await response.json();
    assert.equal(payload.error.code, "file_changed");
    assert.equal(await readFile(resolve(root, filePath), "utf8"), "外部程序的新内容");
  });

  test("deletes an unchanged editable file but rejects cross-origin deletion", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const loaded = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    ).then((response) => response.json());

    const rejected = await fetch(`${baseUrl}/api/file`, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        Origin: "https://example.com",
      },
      body: JSON.stringify({
        path: filePath,
        expectedVersion: loaded.version,
      }),
    });
    assert.equal(rejected.status, 403);
    assert.equal((await rejected.json()).error.code, "invalid_origin");
    assert.equal(await readFile(resolve(root, filePath), "utf8"), "初稿");

    const deletedResponse = await fetch(`${baseUrl}/api/file`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: filePath,
        expectedVersion: loaded.version,
      }),
    });
    assert.equal(deletedResponse.status, 200);
    const deleted = await deletedResponse.json();
    assert.deepEqual(deleted, { ok: true, path: filePath });
    await assert.rejects(
      readFile(resolve(root, filePath), "utf8"),
      (error) => error?.code === "ENOENT",
    );
  });

  test("does not delete a file changed after it was opened", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const loaded = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    ).then((response) => response.json());

    await new Promise((accept) => setTimeout(accept, 20));
    await writeFile(resolve(root, filePath), "外部程序的新内容", "utf8");

    const response = await fetch(`${baseUrl}/api/file`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: filePath,
        expectedVersion: loaded.version,
      }),
    });
    assert.equal(response.status, 409);
    assert.equal((await response.json()).error.code, "file_changed");
    assert.equal(await readFile(resolve(root, filePath), "utf8"), "外部程序的新内容");
  });

  test("accepts only one of several simultaneous saves based on the same version", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const loaded = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    ).then((response) => response.json());

    const responses = await Promise.all(
      Array.from({ length: 8 }, (_, index) =>
        fetch(`${baseUrl}/api/file`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            path: filePath,
            content: `并发写入-${index}`,
            expectedVersion: loaded.version,
          }),
        }),
      ),
    );
    const statuses = responses.map((response) => response.status);
    assert.equal(statuses.filter((status) => status === 200).length, 1, statuses);
    assert.equal(statuses.filter((status) => status === 409).length, 7, statuses);
    assert.match(await readFile(resolve(root, filePath), "utf8"), /^并发写入-[0-7]$/);
  });

  test("serializes simultaneous save and delete operations on the same version", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const loaded = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
    ).then((response) => response.json());
    const versionedPath = { path: filePath, expectedVersion: loaded.version };

    const [saved, deleted] = await Promise.all([
      fetch(`${baseUrl}/api/file`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...versionedPath, content: "保存胜出时的正文" }),
      }),
      fetch(`${baseUrl}/api/file`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(versionedPath),
      }),
    ]);
    assert.deepEqual([saved.status, deleted.status].sort(), [200, 409]);
    if (saved.status === 200) {
      assert.equal(await readFile(resolve(root, filePath), "utf8"), "保存胜出时的正文");
    } else {
      await assert.rejects(
        readFile(resolve(root, filePath), "utf8"),
        (error) => error?.code === "ENOENT",
      );
    }
  });

  test("rejects unsupported files, traversal, and malformed JSON", async () => {
    const root = await createWorkspace();
    const baseUrl = await startServer(root);

    const unsupported = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent("长篇/示例书/封面.png")}`,
    );
    assert.equal(unsupported.status, 415);

    const traversal = await fetch(
      `${baseUrl}/api/file?path=${encodeURIComponent("../outside.md")}`,
    );
    assert.equal(traversal.status, 403);

    const malformed = await fetch(`${baseUrl}/api/file`, {
      method: "PUT",
      body: "{bad",
    });
    assert.equal(malformed.status, 400);
    assert.equal((await malformed.json()).error.code, "invalid_json");

    const versionless = await fetch(`${baseUrl}/api/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: "长篇/示例书/正文/第001章.md",
        content: "不能无版本覆盖",
      }),
    });
    assert.equal(versionless.status, 400);
    assert.equal((await versionless.json()).error.code, "missing_file_version");

    // 删除同样必须带版本号：409 那道比较挡不住它（NaN > 0.5 恒为 false），
    // 少了这条断言，去掉守卫也能一路绿灯把章节删干净。
    const chapterPath = "长篇/示例书/正文/第001章.md";
    const versionlessDelete = await fetch(`${baseUrl}/api/file`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: chapterPath }),
    });
    assert.equal(versionlessDelete.status, 400);
    assert.equal((await versionlessDelete.json()).error.code, "missing_file_version");
    assert.equal(await readFile(resolve(root, chapterPath), "utf8"), "初稿");
  });

  test("keeps the saved file's permission bits instead of letting umask narrow them", async (context) => {
    if (process.platform === "win32") {
      context.skip("Windows 不使用 POSIX 权限位");
      return;
    }
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const filePath = "长篇/示例书/正文/第001章.md";
    const absolutePath = resolve(root, filePath);
    await chmod(absolutePath, 0o664);

    const previousUmask = process.umask(0o022);
    try {
      const loaded = await fetch(
        `${baseUrl}/api/file?path=${encodeURIComponent(filePath)}`,
      ).then((response) => response.json());
      const saved = await fetch(`${baseUrl}/api/file`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: filePath,
          content: "改过的正文",
          expectedVersion: loaded.version,
        }),
      });
      assert.equal(saved.status, 200);
      assert.equal((await stat(absolutePath)).mode & 0o777, 0o664);
    } finally {
      process.umask(previousUmask);
    }
  });

  test("still serves the rest of the workspace when one library directory is unreadable", async (context) => {
    if (process.platform === "win32" || process.getuid?.() === 0) {
      context.skip("当前平台或用户无法制造不可读目录");
      return;
    }
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    const libraryRoot = resolve(root, "拆文库");
    await chmod(libraryRoot, 0o000);
    try {
      const response = await fetch(`${baseUrl}/api/workspace`);
      assert.equal(response.status, 200);
      const payload = await response.json();
      assert.deepEqual(payload.libraries, []);
      assert.equal(payload.limits.truncated, true);
      assert.equal(payload.limits.truncatedByReadError, true);
      assert.deepEqual(
        payload.scanErrors.map(({ path, code }) => ({ path, code })),
        [{ path: "拆文库", code: "EACCES" }],
      );
      assert.deepEqual(
        payload.projects.map((entry) => entry.path),
        ["长篇/示例书"],
      );
    } finally {
      await chmod(libraryRoot, 0o755);
    }
  });

  test("reports an actionable error when the workspace root itself is unreadable", async (context) => {
    if (process.platform === "win32" || process.getuid?.() === 0) {
      context.skip("当前平台或用户无法制造不可读目录");
      return;
    }
    const root = await createWorkspace();
    const baseUrl = await startServer(root);
    await chmod(root, 0o000);
    try {
      const response = await fetch(`${baseUrl}/api/workspace`);
      assert.equal(response.status, 403);
      const payload = await response.json();
      assert.equal(payload.error.code, "workspace_unreadable");
      assert.match(payload.error.message, /工作区目录无法读取/);
    } finally {
      await chmod(root, 0o755);
    }
  });
});

async function createCandidateListingWorkspace() {
  const root = await mkdtemp(resolve(tmpdir(), "oh-story-dashboard-candidates-"));
  temporaryDirectories.push(root);
  const book = resolve(root, "长篇", "候选书");
  await mkdir(resolve(book, "正文"), { recursive: true });
  await mkdir(resolve(book, "大纲"), { recursive: true });
  await mkdir(resolve(book, "骨架"), { recursive: true });
  await mkdir(resolve(book, "候选", "_历史"), { recursive: true });
  await writeFile(resolve(book, "正文", "第001章_旧稿.md"), "# 第001章 旧稿\n正文。\n", "utf8");
  await writeFile(resolve(book, "大纲", "细纲_第002章.md"), "# 细纲\n", "utf8");
  await writeFile(resolve(book, "骨架", "第002章_骨架.md"), "# 骨架\n", "utf8");
  await writeFile(resolve(book, "候选", "第002章_新章.md"), "# 第002章 新章\n候选正文。\n", "utf8");
  await writeFile(resolve(book, "候选", "第002章_追踪事务.json"), "{}", "utf8");
  await writeFile(resolve(book, "候选", "第003章_无事务.md"), "# 第003章\n候选正文。\n", "utf8");
  await writeFile(resolve(book, "候选", "_历史", "第001章_废稿.md"), "已归档", "utf8");
  await writeFile(resolve(book, "候选", "说明.txt"), "非候选", "utf8");
  return { root, book };
}

const pythonAvailable = ["python3", "python", "py"].some(
  (command) => spawnSync(command, ["--version"], { stdio: "ignore" }).status === 0,
);

describe("candidate review listing filters and HTTP contract", () => {
  test("lists prose candidates with context paths and skips history, transactions, and non-markdown", async () => {
    const { root } = await createCandidateListingWorkspace();
    const listing = await listWorkspaceCandidates(root);

    assert.equal(listing.total, 2);
    assert.equal(listing.projects.length, 1);
    const [project] = listing.projects;
    assert.equal(project.name, "候选书");
    assert.deepEqual(
      project.candidates.map((candidate) => candidate.chapter),
      [2, 3],
    );

    const [second, third] = project.candidates;
    assert.equal(second.hasTransaction, true);
    assert.equal(second.finalExists, false);
    assert.equal(second.path, "长篇/候选书/候选/第002章_新章.md");
    assert.equal(second.outlinePath, "长篇/候选书/大纲/细纲_第002章.md");
    assert.equal(second.skeletonPath, "长篇/候选书/骨架/第002章_骨架.md");
    assert.equal(second.previousFinalPath, "长篇/候选书/正文/第001章_旧稿.md");
    assert.equal(third.hasTransaction, false);
    assert.equal(third.outlinePath, null);
    // 归档区与事务/txt 文件绝不能混进待审列表，否则一键采用会打到错误对象上
    assert.ok(!project.candidates.some((candidate) => candidate.name.includes("废稿")));
    assert.ok(!project.candidates.some((candidate) => candidate.name.endsWith(".txt")));
  });

  test("serves candidates over HTTP and rejects invalid action payloads", async () => {
    const { root } = await createCandidateListingWorkspace();
    const baseUrl = await startServer(root);

    const listing = await fetch(`${baseUrl}/api/candidates`).then((response) => response.json());
    assert.equal(listing.total, 2);

    const invalidAction = await fetch(`${baseUrl}/api/candidates/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "publish", project: "长篇/候选书", chapter: 2 }),
    });
    assert.equal(invalidAction.status, 400);

    const invalidChapter = await fetch(`${baseUrl}/api/candidates/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reject", project: "长篇/候选书", chapter: 0 }),
    });
    assert.equal(invalidChapter.status, 400);

    // 版本校验在解析工程目录之前，所以要给一个格式合法的版本才能测到越界防护本身
    const outsideWorkspace = await fetch(`${baseUrl}/api/candidates/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: "reject",
        project: "../外部",
        chapter: 2,
        candidateVersion: "a".repeat(64),
      }),
    });
    assert.equal(outsideWorkspace.status, 403);

    const crossOrigin = await fetch(`${baseUrl}/api/candidates/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "http://evil.example" },
      body: JSON.stringify({ action: "reject", project: "长篇/候选书", chapter: 2 }),
    });
    assert.equal(crossOrigin.status, 403);
  });

  test("reject archives the candidate through candidate-commit.py", { skip: !pythonAvailable }, async () => {
    const { root, book } = await createCandidateListingWorkspace();
    const before = await listWorkspaceCandidates(root);
    const third = before.projects[0].candidates.find((candidate) => candidate.chapter === 3);
    const result = await runCandidateAction(root, {
      action: "reject",
      project: "长篇/候选书",
      chapter: 3,
      rewrite: true,
      candidateVersion: third.candidateVersion,
    });

    assert.equal(result.ok, true);
    assert.equal(result.result.action, "rewrite");
    await assert.rejects(stat(resolve(book, "候选", "第003章_无事务.md")));
    const listing = await listWorkspaceCandidates(root);
    assert.deepEqual(listing.projects[0].candidates.map((candidate) => candidate.chapter), [2]);
  });

  test("promote without a replayable transaction is refused fail-closed", { skip: !pythonAvailable }, async () => {
    const { root, book } = await createCandidateListingWorkspace();
    const before = await listWorkspaceCandidates(root);
    const third = before.projects[0].candidates.find((candidate) => candidate.chapter === 3);
    // 没有追踪事务就拿不到状态版本，采用在调用工具之前就被拒——比落到工具再退出更早的 fail-closed
    assert.equal(third.expectedStateRevision, null);
    await assert.rejects(
      runCandidateAction(root, {
        action: "promote",
        project: "长篇/候选书",
        chapter: 3,
        candidateVersion: third.candidateVersion,
        expectedStateRevision: third.expectedStateRevision,
      }),
      (error) => {
        assert.ok(error instanceof DashboardError);
        assert.equal(error.status, 400);
        assert.equal(error.code, "missing_state_revision");
        return true;
      },
    );
    // 采用被拒后候选必须原地保留，作者可以修事务后重试
    await stat(resolve(book, "候选", "第003章_无事务.md"));
  });
});
