import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const account = { user: { id: 1, email: "owner@example.test", role: "admin" }, csrf_token: "old-csrf" };
const renewed = { ...account, csrf_token: "new-csrf" };
const fieldLabels = ["氏名", "会社名", "部署", "役職", "メールアドレス", "電話番号", "住所", "Webサイト"];
const values = ["テスト 太郎", "架空会社", "営業部", "担当", "card@example.test", "03-0000-0000", "架空住所", "https://example.test"];
const image = (name = "first.png") => new File(["synthetic image"], name, { type: "image/png" });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
type Handler = (path: string, init: RequestInit) => Response | Promise<Response> | undefined;
let handler: Handler;
let fetchMock: ReturnType<typeof vi.fn>;
let objectId = 0;

beforeEach(() => {
  history.replaceState(null, "", "/#/new");
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("fetch", fetchMock = vi.fn(async (input: string, init: RequestInit = {}) => {
    const response = await handler(String(input), init);
    if (response) return response;
    if (input === "/api/auth/me") return json(account);
    if (input === "/api/people/options") return json({ items: [{ id: 7, label: "同姓同名 / 会社 / #7" }] });
    if (String(input).startsWith("/api/cards?")) return json({ items: [], total: 0 });
    if (input === "/api/auth/logout") return new Response(null, { status: 204 });
    throw new Error("Unexpected API call: " + input);
  }));
  handler = () => undefined;
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:preview-" + ++objectId) });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function draft() {
  const user = userEvent.setup();
  const view = render(<App />);
  const file = image();
  await user.upload(await screen.findByLabelText("名刺画像を選択"), file);
  for (let i = 0; i < fieldLabels.length; i++)
    await user.type(screen.getByLabelText(new RegExp("^" + fieldLabels[i])), values[i]);
  await screen.findByRole("option", { name: "同姓同名 / 会社 / #7" });
  await user.selectOptions(screen.getByLabelText("人物の紐付け"), "7");
  return { user, file, ...view };
}

function expectDraft(preserved: boolean) {
  for (let i = 0; i < fieldLabels.length; i++)
    expect((screen.getByLabelText(new RegExp("^" + fieldLabels[i])) as HTMLInputElement).value).toBe(preserved ? values[i] : "");
  expect((screen.getByLabelText("人物の紐付け") as HTMLSelectElement).value).toBe(preserved ? "7" : "");
}

async function login(user: ReturnType<typeof userEvent.setup>, next = renewed) {
  handler = ((previous) => (path, init) => path === "/api/auth/login" ? json(next) : previous(path, init))(handler);
  const form = within((await screen.findByRole("heading", { name: "再ログイン" })).closest("main")!);
  await user.type(form.getByLabelText("パスワード"), "synthetic-password");
  await user.click(form.getByRole("button", { name: "ログイン" }));
}

describe("registration recovery", () => {
  it("keeps image, all edits, selected person and idempotency key after expiry and same-user login", async () => {
    const sent: FormData[] = [];
    handler = (path, init) => {
      if (path === "/api/cards" && init.method === "POST") {
        sent.push(init.body as FormData);
        return json({ message: sent.length === 1 ? "セッションが切れました。" : "保存失敗" }, sent.length === 1 ? 401 : 503);
      }
    };
    const { user, file } = await draft();
    await user.click(screen.getByRole("button", { name: "名刺を登録する" }));
    await login(user);
    await screen.findByRole("button", { name: "名刺を登録する" });
    expectDraft(true);
    expect(screen.getByText(file.name)).toBeTruthy();
    expect(sent).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "名刺を登録する" }));
    await screen.findByText("保存失敗");
    expect(sent).toHaveLength(2);
    expect(JSON.parse(String(sent[1].get("data")))).toEqual(JSON.parse(String(sent[0].get("data"))));
    expect((sent[1].get("image") as File).name).toBe(file.name);
    expect(new Headers(fetchMock.mock.calls.filter(([path]) => path === "/api/cards")[1][1].headers).get("X-CSRF-Token")).toBe("new-csrf");
  });

  it("clears the draft when reauthentication returns a different user", async () => {
    handler = (path, init) => path === "/api/cards" && init.method === "POST" ? json({ message: "期限切れ" }, 401) : undefined;
    const { user } = await draft();
    await user.click(screen.getByRole("button", { name: "名刺を登録する" }));
    await login(user, { user: { id: 2, email: "other@example.test", role: "admin" }, csrf_token: "other-csrf" });
    await screen.findByRole("heading", { name: "名刺一覧" });
    await user.click(screen.getByRole("link", { name: "名刺を登録" }));
    await screen.findByRole("heading", { name: "名刺を登録" });
    expectDraft(false);
    expect(screen.queryByText("first.png")).toBeNull();
  });

  it("clears the draft on explicit logout even when the same user logs in again", async () => {
    const { user } = await draft();
    await user.click(screen.getAllByRole("button", { name: "ログアウト" })[0]);
    await screen.findByRole("heading", { name: "ログイン" });
    handler = (path) => path === "/api/auth/login" ? json(renewed) : undefined;
    await user.type(screen.getByLabelText("メールアドレス"), account.user.email);
    await user.type(screen.getByLabelText("パスワード"), "synthetic-password");
    await user.click(screen.getByRole("button", { name: "ログイン" }));
    await screen.findByRole("heading", { name: "名刺一覧" });
    await user.click(screen.getByRole("link", { name: "名刺を登録" }));
    await screen.findByRole("heading", { name: "名刺を登録" });
    expectDraft(false);
    expect(screen.queryByText("first.png")).toBeNull();
  });

  it("keeps the complete draft after ordinary extraction and save errors", async () => {
    handler = (path, init) => path === "/api/extract" || (path === "/api/cards" && init.method === "POST") ? json({ message: "処理失敗" }, 503) : undefined;
    const { user } = await draft();
    await user.click(screen.getByRole("button", { name: "AIで名刺を読み取る" }));
    await screen.findByText(/処理失敗 手入力/);
    expectDraft(true);
    await user.click(screen.getByRole("button", { name: "名刺を登録する" }));
    await screen.findByText("処理失敗");
    expectDraft(true);
    expect(screen.getByText("first.png")).toBeTruthy();
  });
});

describe("image replacement", () => {
  it("clears all fields and the person only after choosing a different card", async () => {
    const { user } = await draft();
    const oldPreview = screen.getByAltText("登録する名刺のプレビュー").getAttribute("src");
    await user.upload(screen.getByLabelText("名刺画像を選択"), image("second.png"));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expectDraft(true);
    expect(screen.getByAltText("登録する名刺のプレビュー").getAttribute("src")).toBe(oldPreview);
    expect((screen.getByRole("button", { name: "名刺を登録する" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "別の名刺としてクリア" }));
    expectDraft(false);
    expect(screen.getByText("second.png")).toBeTruthy();
    expect(screen.getByAltText("登録する名刺のプレビュー").getAttribute("src")).not.toBe(oldPreview);
  });

  it("keeps all fields and person for a retaken photo", async () => {
    const { user } = await draft();
    await user.upload(screen.getByLabelText("名刺画像を選択"), image("retaken.png"));
    await user.click(screen.getByRole("button", { name: "同じ名刺の撮り直しとして保持" }));
    expectDraft(true);
    expect(screen.getByText("retaken.png")).toBeTruthy();
  });

  it("cancels without changing the preview or draft and allows selecting the same file again", async () => {
    const { user, file } = await draft();
    const oldPreview = screen.getByAltText("登録する名刺のプレビュー").getAttribute("src");
    await user.upload(screen.getByLabelText("名刺画像を選択"), file);
    await user.click(screen.getByRole("button", { name: "キャンセル" }));
    expectDraft(true);
    expect(screen.getByAltText("登録する名刺のプレビュー").getAttribute("src")).toBe(oldPreview);
    await user.upload(screen.getByLabelText("名刺画像を選択"), file);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("rejects invalid images without staging replacement or changing the current draft", async () => {
    const { user } = await draft();
    const oldPreview = screen.getByAltText("登録する名刺のプレビュー").getAttribute("src");
    const unfiltered = userEvent.setup({ applyAccept: false });
    await unfiltered.upload(screen.getByLabelText("名刺画像を選択"), new File(["bad"], "bad.gif", { type: "image/gif" }));
    await screen.findByText("JPEGまたはPNGの画像を選択してください。");
    expectDraft(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByAltText("登録する名刺のプレビュー").getAttribute("src")).toBe(oldPreview);
    expect(screen.getByText("first.png")).toBeTruthy();
  });

  it("allows the exact same image to be selected again after a successful save", async () => {
    handler = (path, init) => {
      if (path === "/api/cards" && init.method === "POST") return json({ id: 99 });
      if (path === "/api/cards/99") return json({ id: 99, name: "保存済み", created_by_email: "owner@example.test", created_at: "2026-01-01T00:00:00", person_id: 7 });
    };
    const { user, file } = await draft();
    await user.click(screen.getByRole("button", { name: "名刺を登録する" }));
    await screen.findByRole("heading", { name: "保存済み" });
    await user.click(screen.getByRole("link", { name: "名刺を登録" }));
    await user.upload(await screen.findByLabelText("名刺画像を選択"), file);
    expect(screen.getByText("first.png")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect((screen.getByRole("button", { name: "AIで名刺を読み取る" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("permission refresh", () => {
  it("shows unknown permissions on failure, preserves the error during other UI changes, and recovers through retry", async () => {
    history.replaceState(null, "", "/#/admin");
    let failed = true;
    handler = (path) => {
      if (path === "/api/admin/users") return json({ items: [account.user, { id: 2, email: "member@example.test", role: "user" }] });
      if (path.startsWith("/api/admin/grant-targets?")) return json({ items: [{ id: 3, label: "架空企業 #3" }] });
      if (path === "/api/admin/users/2/grants") return failed ? json({ message: "一時的な障害" }, 503) : json({ items: [{ id: 4, scope: "company", target_id: 3, label: "架空企業 #3" }] });
    };
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText(/閲覧許可を取得できませんでした/);
    expect(screen.queryByText("個別の閲覧許可はありません。")).toBeNull();
    expect(screen.getByText("取得失敗")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /member@example.test/ }));
    expect(screen.getByText(/閲覧許可を取得できませんでした/)).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("企業を選択"), "3");
    expect((screen.getByRole("button", { name: "閲覧許可を付与" }) as HTMLButtonElement).disabled).toBe(true);
    failed = false;
    await user.click(screen.getByRole("button", { name: "許可を再取得" }));
    await waitFor(() => expect(screen.queryByText(/閲覧許可を取得できませんでした/)).toBeNull());
    await screen.findByRole("button", { name: "架空企業 #3 の許可を解除" });
    expect(screen.getByText("1 件")).toBeTruthy();
  });
});
