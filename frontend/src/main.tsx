import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type User = { id: number; email: string; role: "admin" | "user" };
type Auth = { user: User; csrf_token: string };
const fields = [
  ["name", "氏名"],
  ["company_name", "会社名"],
  ["department", "部署"],
  ["title", "役職"],
  ["email", "メールアドレス"],
  ["phone", "電話番号"],
  ["address", "住所"],
  ["website", "Webサイト"],
] as const;
type Field = (typeof fields)[number][0];
type Fields = Record<Field, string>;
type Card = Fields & {
  id: number;
  company_id: number | null;
  department_id: number | null;
  person_id: number;
  created_by: number;
  created_by_email: string;
  created_at: string;
};
type Option = { id: number; label: string };
type Scope = "company" | "department" | "person";
type Grant = { id: number; scope: Scope; target_id: number; label: string };
const scopes: Record<Scope, string> = {
  company: "企業",
  department: "部署",
  person: "人物",
};
const blank = (): Fields =>
  Object.fromEntries(fields.map(([key]) => [key, ""])) as Fields;
const date = (value: string) =>
  new Date(
    value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z",
  ).toLocaleString("ja-JP");
class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
async function api<T>(
  path: string,
  csrf = "",
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (csrf && options.method && !["GET", "HEAD"].includes(options.method))
    headers.set("X-CSRF-Token", csrf);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...options,
      headers,
      credentials: "same-origin",
    });
  } catch {
    throw new Error(
      "サーバーに接続できません。接続を確認して、もう一度お試しください。",
    );
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      typeof error?.message === "string"
        ? error.message
        : response.status === 401
          ? "ログインの有効期限が切れました。再度ログインしてください。"
          : "処理に失敗しました。入力内容を確認して再度お試しください。",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const message = (error: unknown) =>
  error instanceof Error ? error.message : "処理に失敗しました。";
function Icon({
  name,
  size = 20,
}: {
  name:
    | "cards"
    | "plus"
    | "users"
    | "search"
    | "arrow"
    | "upload"
    | "spark"
    | "logout";
  size?: number;
}) {
  const paths = {
    cards: (
      <>
        <rect x="3" y="5" width="18" height="14" rx="3" />
        <path d="M7 10h4m-4 4h10m-2-4h2" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    arrow: <path d="m9 5 7 7-7 7" />,
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" />
      </>
    ),
    spark: (
      <>
        <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
      </>
    ),
    logout: (
      <>
        <path d="M9 4H4v16h5m5-4 4-4-4-4m-6 4h12" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
function Notice({
  children,
  success = false,
}: {
  children: React.ReactNode;
  success?: boolean;
}) {
  return (
    <div
      role={success ? "status" : "alert"}
      className={"notice " + (success ? "success" : "")}
    >
      {children}
    </div>
  );
}
function Loading({ text = "読み込み中…" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {text}
    </div>
  );
}
function Empty({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name="cards" size={30} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Login({ onLogin }: { onLogin: (auth: Auth) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(
        await api<Auth>("/auth/login", "", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        }),
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Icon name="cards" size={27} />
          </span>
          <span>
            名刺ノート<small>MEISHI NOTE</small>
          </span>
        </div>
        <div>
          <span className="eyebrow">YOUR CONNECTIONS, ORGANIZED</span>
          <h1>
            出会いを、
            <br />
            次のつながりへ。
          </h1>
          <p>
            名刺を読み取り、情報を整え、
            <br />
            必要な人と共有する。チームの名刺管理をひとつに。
          </p>
        </div>
        <span className="story-footer">BUSINESS CARD WORKSPACE</span>
      </div>
      <section className="login-form">
        <div className="login-inner">
          <span className="eyebrow teal">WELCOME BACK</span>
          <h2>ログイン</h2>
          <p className="muted">登録されたアカウントでログインしてください。</p>
          {error && <Notice>{error}</Notice>}
          <form onSubmit={submit}>
            <label>
              メールアドレス
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
              />
            </label>
            <label>
              パスワード
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button className="primary wide" disabled={busy}>
              {busy ? "ログイン中…" : "ログイン"}
              <Icon name="arrow" size={17} />
            </button>
          </form>
          <p className="login-help">
            アカウントが必要な場合は管理者にお問い合わせください。
          </p>
        </div>
      </section>
    </main>
  );
}
function CardList({
  auth,
  open,
  register,
  changed,
}: {
  auth: Auth;
  open: (id: number) => void;
  register: () => void;
  changed: number;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<{ items: Card[]; total: number } | null>(
    null,
  );
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const limit = 12;
  useEffect(() => {
    let alive = true;
    setBusy(true);
    setError("");
    api<{ items: Card[]; total: number }>(
      `/cards?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`,
      auth.csrf_token,
    )
      .then((data) => {
        if (alive) setResult(data);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, [query, offset, auth.csrf_token, changed, retry]);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow teal">YOUR CONNECTIONS</span>
          <h1>名刺一覧</h1>
          <p>出会った人と、つながりを見つける。</p>
        </div>
        <button className="primary" onClick={register}>
          <Icon name="plus" />
          名刺を登録
        </button>
      </div>
      <section className="panel">
        <div className="list-toolbar">
          <form
            className="search"
            onSubmit={(e) => {
              e.preventDefault();
              setOffset(0);
              setQuery(search.trim());
            }}
          >
            <Icon name="search" />
            <input
              aria-label="氏名・会社名で検索"
              placeholder="氏名・会社名で検索"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button className="secondary">検索</button>
          </form>
          <span className="result-count">
            {result ? (
              <>
                <strong>{result.total}</strong> 件の名刺
              </>
            ) : (
              "名刺を取得中"
            )}
          </span>
        </div>
        {query && (
          <div className="query-info">
            「{query}」の検索結果{" "}
            <button
              className="text-button"
              onClick={() => {
                setSearch("");
                setQuery("");
                setOffset(0);
              }}
            >
              検索を解除
            </button>
          </div>
        )}
        {error ? (
          <div className="panel-body">
            <Notice>{error}</Notice>
            <button
              className="secondary"
              onClick={() => setRetry((v) => v + 1)}
            >
              再読み込み
            </button>
          </div>
        ) : busy ? (
          <Loading />
        ) : result?.items.length ? (
          <>
            <div className="card-grid">
              {result.items.map((card) => (
                <button
                  className="contact-card"
                  key={card.id}
                  onClick={() => open(card.id)}
                >
                  <div className="contact-top">
                    <span className="avatar">{card.name.slice(0, 1)}</span>
                    <Icon name="arrow" size={17} />
                  </div>
                  <span className="contact-company">
                    {card.company_name || "会社名未登録"}
                  </span>
                  <h3>{card.name}</h3>
                  <p className="contact-role">
                    {[card.department, card.title]
                      .filter(Boolean)
                      .join(" / ") || "部署・役職未登録"}
                  </p>
                  <div className="contact-bottom">
                    <span>{card.email || card.phone || "連絡先未登録"}</span>
                    <small>{date(card.created_at).split(" ")[0]}</small>
                  </div>
                </button>
              ))}
            </div>
            <div className="pagination">
              <span>
                {offset + 1}–{Math.min(offset + limit, result.total)} /{" "}
                {result.total} 件
              </span>
              <div>
                <button
                  className="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((v) => Math.max(0, v - limit))}
                >
                  前へ
                </button>
                <button
                  className="secondary"
                  disabled={offset + limit >= result.total}
                  onClick={() => setOffset((v) => v + limit)}
                >
                  次へ
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            title={
              query
                ? "該当する名刺はありません"
                : "まだ名刺が登録されていません"
            }
          >
            {query
              ? "氏名や会社名の一部を変えて検索してください。"
              : "「名刺を登録」から、最初の1枚を取り込んでみましょう。"}
          </Empty>
        )}
      </section>
      <p className="page-note">
        あなたが登録した名刺と、閲覧が許可された名刺を表示しています。
      </p>
    </>
  );
}
function Registration({
  auth,
  saved,
}: {
  auth: Auth;
  saved: (id: number) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [data, setData] = useState<Fields>(blank);
  const [person, setPerson] = useState("");
  const [people, setPeople] = useState<Option[]>([]);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState<"extract" | "save" | "">("");
  const [peopleError, setPeopleError] = useState("");
  const [peopleRetry, setPeopleRetry] = useState(0);
  const requestId = useRef(crypto.randomUUID());
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  useEffect(() => {
    let alive = true;
    setPeopleError("");
    api<{ items: Option[] }>("/people/options", auth.csrf_token)
      .then((r) => {
        if (alive) setPeople(r.items);
      })
      .catch((e) => {
        if (alive) setPeopleError(message(e));
      });
    return () => {
      alive = false;
    };
  }, [auth.csrf_token, peopleRetry]);
  function choose(next: File | undefined) {
    if (!next) return;
    setError("");
    setInfo("");
    if (!["image/jpeg", "image/png"].includes(next.type)) {
      setError("JPEGまたはPNGの画像を選択してください。");
      return;
    }
    if (next.size > 5 * 1024 * 1024) {
      setError("画像は5MiB以下のファイルを選択してください。");
      return;
    }
    setFile(next);
    requestId.current = crypto.randomUUID();
  }
  function update(key: Field, value: string) {
    setData((v) => ({ ...v, [key]: value }));
    requestId.current = crypto.randomUUID();
  }
  async function extract() {
    if (!file) return;
    setBusy("extract");
    setError("");
    setInfo("");
    const form = new FormData();
    form.append("image", file);
    try {
      const result = await api<{ fields: Fields }>(
        "/extract",
        auth.csrf_token,
        { method: "POST", body: form },
      );
      setData(
        Object.fromEntries(
          fields.map(([key]) => [key, result.fields[key] || ""]),
        ) as Fields,
      );
      requestId.current = crypto.randomUUID();
      setInfo(
        "読み取りが完了しました。元の画像と照らし合わせ、内容を確認・修正してください。",
      );
    } catch (e) {
      setError(message(e) + " 手入力で登録することもできます。");
    } finally {
      setBusy("");
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("名刺画像を選択してください。");
      return;
    }
    if (!data.name.trim()) {
      setError("氏名を入力してください。");
      return;
    }
    setBusy("save");
    setError("");
    setInfo("");
    const form = new FormData();
    form.append("image", file);
    form.append(
      "data",
      JSON.stringify({
        ...data,
        name: data.name.trim(),
        request_id: requestId.current,
        person_id: person ? Number(person) : null,
      }),
    );
    try {
      const card = await api<Card>("/cards", auth.csrf_token, {
        method: "POST",
        body: form,
      });
      setFile(null);
      setData(blank());
      setPerson("");
      setPeopleRetry((v) => v + 1);
      requestId.current = crypto.randomUUID();
      saved(card.id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow teal">ADD A CONNECTION</span>
          <h1>名刺を登録</h1>
          <p>画像を取り込み、読み取った内容を確認して保存します。</p>
        </div>
        <span className="step-badge">画像選択 → 確認・修正 → 登録</span>
      </div>
      {error && <Notice>{error}</Notice>}
      {info && <Notice success>{info}</Notice>}
      <form onSubmit={save} className="registration">
        <section className="panel image-panel">
          <div className="section-title">
            <span className="step-number">01</span>
            <h2>名刺画像</h2>
          </div>
          <div className="image-content">
            <label className={"upload-zone " + (preview ? "has-image" : "")}>
              {preview ? (
                <img src={preview} alt="登録する名刺のプレビュー" />
              ) : (
                <>
                  <span className="upload-icon">
                    <Icon name="upload" size={30} />
                  </span>
                  <strong>クリックして画像を選択</strong>
                  <span>名刺の文字が鮮明な画像をご用意ください</span>
                </>
              )}
              <input
                type="file"
                accept="image/jpeg,image/png"
                aria-label="名刺画像を選択"
                disabled={!!busy}
                onChange={(e) => choose(e.target.files?.[0])}
              />
            </label>
            <div className="file-meta">
              <span>{file ? file.name : "JPEG・PNG / 1枚5MiB以下"}</span>
              {file && <small>{(file.size / 1024).toFixed(0)} KB</small>}
            </div>
            <button
              type="button"
              className="ai-button wide"
              onClick={extract}
              disabled={!file || !!busy}
            >
              <Icon name="spark" />
              {busy === "extract" ? "AIで読み取り中…" : "AIで名刺を読み取る"}
            </button>
            <p className="helper">
              AIは記載された8項目を読み取ります。読み取り結果は保存前に必ず確認してください。手入力でも登録できます。
            </p>
          </div>
        </section>
        <section className="panel fields-panel">
          <div className="section-title">
            <span className="step-number">02</span>
            <h2>確認・修正</h2>
            <span className="muted small">* 必須</span>
          </div>
          <fieldset disabled={!!busy}>
            <div className="field-grid">
              {fields.map(([key, label]) => (
                <label
                  className={
                    key === "address" || key === "website" ? "full" : ""
                  }
                  key={key}
                >
                  {label}
                  {key === "name" && <span className="required"> *</span>}
                  <input
                    value={data[key]}
                    onChange={(e) => update(key, e.target.value)}
                    required={key === "name"}
                    maxLength={key === "name" ? 200 : 1000}
                    autoComplete="off"
                    inputMode={
                      key === "email"
                        ? "email"
                        : key === "phone"
                          ? "tel"
                          : "text"
                    }
                    placeholder={key === "name" ? "例：山田 太郎" : ""}
                  />
                </label>
              ))}
            </div>
            <div className="person-section">
              <label>
                人物の紐付け
                <select
                  value={person}
                  onChange={(e) => {
                    setPerson(e.target.value);
                    requestId.current = crypto.randomUUID();
                  }}
                >
                  <option value="">新しい人物として登録</option>
                  {people.map((p) => (
                    <option value={p.id} key={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <p className="helper">
                同じ人物の別の名刺の場合のみ、既存の人物を選択してください。同姓同名は自動で統合しません。
              </p>
              {peopleError && (
                <>
                  <Notice>{peopleError}</Notice>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => setPeopleRetry((v) => v + 1)}
                  >
                    人物候補を再取得
                  </button>
                </>
              )}
            </div>
          </fieldset>
          <div className="form-footer">
            <span className="helper">元画像と確認済みの情報を保存します</span>
            <button className="primary" disabled={!file || !!busy}>
              {busy === "save" ? "保存中…" : "名刺を登録する"}
              <Icon name="arrow" size={17} />
            </button>
          </div>
        </section>
      </form>
    </>
  );
}
function Detail({
  auth,
  id,
  back,
}: {
  auth: Auth;
  id: number;
  back: () => void;
}) {
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState("");
  const [imageError, setImageError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setCard(null);
    setError("");
    setImageError(false);
    api<Card>(`/cards/${id}`, auth.csrf_token)
      .then((r) => {
        if (alive) setCard(r);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      });
    return () => {
      alive = false;
    };
  }, [id, auth.csrf_token, retry]);
  return (
    <>
      <button className="back-button" onClick={back}>
        ← 名刺一覧に戻る
      </button>
      {error ? (
        <>
          <Notice>{error}</Notice>
          <button className="secondary" onClick={() => setRetry((v) => v + 1)}>
            再読み込み
          </button>
        </>
      ) : !card ? (
        <Loading />
      ) : (
        <>
          <div className="page-heading">
            <div>
              <span className="eyebrow teal">CONNECTION DETAILS</span>
              <h1>{card.name}</h1>
              <p>{card.company_name || "会社名未登録"}</p>
            </div>
            <span className="step-badge">名刺 #{card.id}</span>
          </div>
          <div className="registration detail">
            <section className="panel">
              <div className="section-title">
                <h2>元の名刺画像</h2>
              </div>
              <div className="original-image">
                {imageError ? (
                  <Notice>
                    画像を取得できませんでした。
                    <button
                      className="text-button"
                      onClick={() => setRetry((v) => v + 1)}
                    >
                      再読み込み
                    </button>
                  </Notice>
                ) : (
                  <img
                    key={retry}
                    src={`/api/cards/${card.id}/image?retry=${retry}`}
                    alt={`${card.name}さんの名刺原画像`}
                    onError={() => setImageError(true)}
                  />
                )}
              </div>
            </section>
            <section className="panel">
              <div className="section-title">
                <h2>名刺情報</h2>
              </div>
              <dl className="detail-fields">
                {fields.map(([key, label]) => (
                  <div key={key}>
                    <dt>{label}</dt>
                    <dd>
                      {key === "website" && /^https?:\/\//i.test(card[key]) ? (
                        <a
                          href={card[key]}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {card[key]}
                        </a>
                      ) : (
                        card[key] || <span className="muted">未登録</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="record-meta">
                <p>
                  登録者 <strong>{card.created_by_email}</strong>
                </p>
                <p>
                  登録日時 <strong>{date(card.created_at)}</strong>
                </p>
                <p>
                  人物ID <strong>#{card.person_id}</strong>
                </p>
              </div>
            </section>
          </div>
        </>
      )}
    </>
  );
}
function Admin({ auth }: { auth: Auth }) {
  const [users, setUsers] = useState<User[]>([]);
  const [selected, setSelected] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [scope, setScope] = useState<Scope>("company");
  const [target, setTarget] = useState("");
  const [targets, setTargets] = useState<Option[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingGrants, setLoadingGrants] = useState(false);
  const [loadingTargets, setLoadingTargets] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoadingUsers(true);
    setError("");
    api<{ items: User[] }>("/admin/users", auth.csrf_token)
      .then((r) => {
        if (alive) {
          setUsers(r.items);
          setSelected(
            (v) =>
              v ||
              String(
                r.items.find((u) => u.role === "user")?.id ||
                  r.items[0]?.id ||
                  "",
              ),
          );
        }
      })
      .catch((e) => {
        if (alive) setError(message(e));
      })
      .finally(() => {
        if (alive) setLoadingUsers(false);
      });
    return () => {
      alive = false;
    };
  }, [auth.csrf_token, retry]);
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    setLoadingGrants(true);
    setGrants([]);
    api<{ items: Grant[] }>(`/admin/users/${selected}/grants`, auth.csrf_token)
      .then((r) => {
        if (alive) setGrants(r.items);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      })
      .finally(() => {
        if (alive) setLoadingGrants(false);
      });
    return () => {
      alive = false;
    };
  }, [selected, auth.csrf_token, retry]);
  useEffect(() => {
    let alive = true;
    setTarget("");
    setTargets([]);
    setLoadingTargets(true);
    api<{ items: Option[] }>(
      `/admin/grant-targets?scope=${scope}`,
      auth.csrf_token,
    )
      .then((r) => {
        if (alive) setTargets(r.items);
      })
      .catch((e) => {
        if (alive) setError(message(e));
      })
      .finally(() => {
        if (alive) setLoadingTargets(false);
      });
    return () => {
      alive = false;
    };
  }, [scope, auth.csrf_token, retry]);
  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setBusy("user");
    setError("");
    setSuccess("");
    try {
      const user = await api<User>("/admin/users", auth.csrf_token, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUsers((v) => [...v, user]);
      setSelected(String(user.id));
      setEmail("");
      setPassword("");
      setSuccess(`${user.email} のアカウントを作成しました。`);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }
  async function grant(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !target) return;
    setBusy("grant");
    setError("");
    setSuccess("");
    try {
      const item = await api<Grant>(
        `/admin/users/${selected}/grants`,
        auth.csrf_token,
        {
          method: "POST",
          body: JSON.stringify({ scope, target_id: Number(target) }),
        },
      );
      setGrants((v) => (v.some((g) => g.id === item.id) ? v : [...v, item]));
      setSuccess("閲覧許可を付与しました。");
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }
  async function revoke(item: Grant) {
    setBusy(String(item.id));
    setError("");
    setSuccess("");
    try {
      await api<void>(
        `/admin/users/${selected}/grants/${item.id}`,
        auth.csrf_token,
        { method: "DELETE" },
      );
      setGrants((v) => v.filter((g) => g.id !== item.id));
      setSuccess(
        "閲覧許可を解除しました。別の許可や登録者の権限がある名刺は引き続き閲覧できます。",
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }
  const selectedUser = users.find((u) => String(u.id) === selected);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow teal">TEAM SETTINGS</span>
          <h1>利用者と閲覧許可</h1>
          <p>チームのアカウントと、共有する名刺の範囲を管理します。</p>
        </div>
        <span className="step-badge">管理者専用</span>
      </div>
      {error && (
        <Notice>
          {error}{" "}
          <button
            className="text-button"
            onClick={() => setRetry((v) => v + 1)}
          >
            再読み込み
          </button>
        </Notice>
      )}
      {success && <Notice success>{success}</Notice>}
      <div className="admin-grid">
        <section className="panel">
          <div className="section-title">
            <h2>利用者を追加</h2>
          </div>
          <form className="panel-body stack" onSubmit={createUser}>
            <label>
              メールアドレス
              <input
                type="email"
                required
                value={email}
                disabled={!!busy}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
                placeholder="member@example.com"
              />
            </label>
            <label>
              初期パスワード
              <input
                type="password"
                required
                minLength={12}
                value={password}
                disabled={!!busy}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="12文字以上"
              />
            </label>
            <p className="helper">
              一般利用者として作成します。初期パスワードはアプリ外で本人に共有してください。
            </p>
            <button className="primary" disabled={!!busy}>
              {busy === "user" ? "作成中…" : "利用者を追加"}
            </button>
          </form>
          <div className="user-list">
            <h3>
              登録済みの利用者 <span>{users.length}</span>
            </h3>
            {loadingUsers ? (
              <Loading />
            ) : users.length ? (
              users.map((user) => (
                <button
                  className={
                    "user-row " +
                    (selected === String(user.id) ? "selected" : "")
                  }
                  disabled={!!busy}
                  key={user.id}
                  onClick={() => {
                    setSelected(String(user.id));
                    setSuccess("");
                    setError("");
                  }}
                >
                  <span className="mini-avatar">
                    {user.email.slice(0, 1).toUpperCase()}
                  </span>
                  <span>
                    {user.email}
                    <small>ID #{user.id}</small>
                  </span>
                  <span className="role-tag">
                    {user.role === "admin" ? "管理者" : "利用者"}
                  </span>
                </button>
              ))
            ) : (
              <p className="helper">利用者を取得できませんでした。</p>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="section-title">
            <h2>閲覧許可</h2>
          </div>
          <div className="panel-body">
            <label>
              対象の利用者
              <select
                value={selected}
                disabled={!!busy || loadingUsers}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setSuccess("");
                  setError("");
                }}
              >
                <option value="" disabled>
                  利用者を選択
                </option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.email} / #{u.id}
                    {u.role === "admin" ? "（管理者）" : ""}
                  </option>
                ))}
              </select>
            </label>
            {selectedUser?.role === "admin" && (
              <p className="admin-note">管理者はすべての名刺を閲覧できます。</p>
            )}
            <form className="grant-form" onSubmit={grant}>
              <h3>新しい許可を付与</h3>
              <div className="scope-tabs" role="group" aria-label="許可の範囲">
                {(Object.keys(scopes) as Scope[]).map((s) => (
                  <button
                    type="button"
                    disabled={!!busy}
                    aria-pressed={scope === s}
                    className={scope === s ? "active" : ""}
                    key={s}
                    onClick={() => setScope(s)}
                  >
                    {scopes[s]}
                  </button>
                ))}
              </div>
              <label>
                {scopes[scope]}を選択
                <select
                  value={target}
                  disabled={!!busy || loadingTargets}
                  required
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="">
                    {loadingTargets
                      ? "読み込み中…"
                      : targets.length
                        ? "対象を選択してください"
                        : "対象がありません"}
                  </option>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="primary"
                disabled={!!busy || !selected || !target || loadingGrants}
              >
                {busy === "grant" ? "付与中…" : "閲覧許可を付与"}
              </button>
            </form>
            <h3 className="grants-title">
              現在の許可 <span>{grants.length} 件</span>
            </h3>
            {loadingGrants ? (
              <Loading />
            ) : grants.length ? (
              <ul className="grant-list">
                {grants.map((g) => (
                  <li key={g.id}>
                    <div>
                      <span className="scope-tag">{scopes[g.scope]}</span>
                      <p>{g.label}</p>
                    </div>
                    <button
                      className="danger-button"
                      disabled={!!busy}
                      onClick={() => revoke(g)}
                      aria-label={`${g.label} の許可を解除`}
                    >
                      {busy === String(g.id) ? "解除中…" : "解除"}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="grant-empty">個別の閲覧許可はありません。</p>
            )}
            <p className="helper">
              企業・部署・人物のいずれかの許可で閲覧できます。登録した本人は許可がなくても自分の名刺を閲覧できます。
            </p>
          </div>
        </section>
      </div>
    </>
  );
}
function App() {
  const [auth, setAuth] = useState<Auth | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [initError, setInitError] = useState("");
  const [route, setRoute] = useState(location.hash.slice(1) || "/");
  const [revision, setRevision] = useState(0);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [initializedRegister, setInitializedRegister] = useState(false);
  useEffect(() => {
    const change = () => setRoute(location.hash.slice(1) || "/");
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  async function initialize() {
    setInitializing(true);
    setInitError("");
    try {
      setAuth(await api<Auth>("/auth/me"));
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401))
        setInitError(message(e));
    } finally {
      setInitializing(false);
    }
  }
  useEffect(() => {
    void initialize();
  }, []);
  useEffect(() => {
    if (route === "/new") setInitializedRegister(true);
  }, [route]);
  function navigate(path: string) {
    location.hash = path;
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  async function logout() {
    setLoggingOut(true);
    setLogoutError("");
    try {
      await api<void>("/auth/logout", auth?.csrf_token, { method: "POST" });
      setAuth(null);
      setInitializedRegister(false);
      navigate("/");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setAuth(null);
        setInitializedRegister(false);
        navigate("/");
      } else setLogoutError(message(e));
    } finally {
      setLoggingOut(false);
    }
  }
  if (initializing)
    return (
      <main className="startup">
        <Loading text="ワークスペースを開いています…" />
      </main>
    );
  if (initError)
    return (
      <main className="startup">
        <div>
          <Notice>{initError}</Notice>
          <button className="primary" onClick={initialize}>
            再接続
          </button>
        </div>
      </main>
    );
  if (!auth) return <Login onLogin={setAuth} />;
  const detailId = /^\/cards\/(\d+)$/.exec(route)?.[1];
  return (
    <div className="workspace">
      <aside className="sidebar">
        <a href="#/" className="brand">
          <span className="brand-icon">
            <Icon name="cards" size={25} />
          </span>
          <span>
            名刺ノート<small>MEISHI NOTE</small>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          <a className={route === "/" || detailId ? "active" : ""} href="#/">
            <Icon name="cards" />
            名刺一覧
          </a>
          <a className={route === "/new" ? "active" : ""} href="#/new">
            <Icon name="plus" />
            名刺を登録
          </a>
          {auth.user.role === "admin" && (
            <>
              <div className="nav-label">MANAGEMENT</div>
              <a className={route === "/admin" ? "active" : ""} href="#/admin">
                <Icon name="users" />
                利用者と閲覧許可
              </a>
            </>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="account">
            <span className="account-avatar">
              {auth.user.email.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong title={auth.user.email}>{auth.user.email}</strong>
              <small>
                {auth.user.role === "admin" ? "管理者" : "一般利用者"}
              </small>
            </div>
          </div>
          <button className="logout" onClick={logout} disabled={loggingOut}>
            <Icon name="logout" size={18} />
            {loggingOut ? "ログアウト中…" : "ログアウト"}
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <span>つながりを、チームの力に。</span>
          <span className="workspace-tag">
            <i />
            名刺ワークスペース
          </span>
          <button
            className="mobile-logout"
            onClick={logout}
            disabled={loggingOut}
          >
            {loggingOut ? "ログアウト中…" : "ログアウト"}
          </button>
        </header>
        <main className="main-content">
          {logoutError && <Notice>{logoutError}</Notice>}
          {initializedRegister && (
            <div hidden={route !== "/new"}>
              <Registration
                auth={auth}
                saved={(id) => {
                  setRevision((v) => v + 1);
                  navigate(`/cards/${id}`);
                }}
              />
            </div>
          )}
          {route === "/new" ? null : detailId ? (
            <Detail
              auth={auth}
              id={Number(detailId)}
              back={() => navigate("/")}
            />
          ) : route === "/admin" && auth.user.role === "admin" ? (
            <Admin auth={auth} />
          ) : (
            <CardList
              auth={auth}
              open={(id) => navigate(`/cards/${id}`)}
              register={() => navigate("/new")}
              changed={revision}
            />
          )}
        </main>
        <footer className="workspace-footer">
          MEISHI NOTE <span>一枚の名刺から、つながりを育てる。</span>
        </footer>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
