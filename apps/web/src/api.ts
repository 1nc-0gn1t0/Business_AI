import type { components } from "./api-schema";

export type Schemas = components["schemas"];
export type Profile = Schemas["BusinessProfile-Output"];
export type Conversation = Schemas["ConversationView"];
export type Dataset = Schemas["DatasetView"];
export type Ranking = Schemas["RankingCollection"];
export type Credential = { id: string; token: string };
const storageKey = "business-ai.guest.v1";

export function readCredential(): Credential | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    return saved &&
      typeof saved.id === "string" &&
      typeof saved.token === "string"
      ? saved
      : null;
  } catch {
    return null;
  }
}
export function saveCredential(value: Credential) {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
const messages: Record<string, string> = {
  demo_data_disabled:
    "Демонстрационные данные запрещены текущим режимом или отключены сервером.",
  provider_version_not_found:
    "Версия источника недоступна. Обновите список и выберите набор заново.",
  provider_dataset_invalid:
    "Набор не прошёл проверку целостности. Данные не подставлены.",
  provider_not_integrated:
    "Источник ещё не подключён. Данные отсутствуют, подмена не выполняется.",
  walking_graph_version_not_found:
    "Запрошенная версия дорожного графа недоступна. Обновите граф и повторите расчёт.",
  lead_consent_changed:
    "Согласие изменилось после подготовки. Сохраните новую версию черновика и заново подтвердите её состав.",
  consent_required_assistant:
    "Согласие на использование ассистента отсутствует или отозвано. Управление согласиями — в разделе продуктов.",
  consent_required_demo_lead:
    "Нужно отдельное действующее согласие на подготовку и демонстрационную передачу заявки.",
  consent_revision_conflict:
    "Согласие изменилось другим запросом. Обновите согласия и повторите действие.",
  consent_text_changed:
    "Версия текста согласия изменилась. Прочитайте актуальный текст.",
  lead_revision_conflict:
    "Черновик изменился. Обновите заявку и заново проверьте её состав.",
  lead_profile_stale:
    "Профиль изменён или не подтверждён. Подтвердите его, обновите и заново подтвердите черновик.",
  lead_payload_conflict:
    "Состав заявки изменился. Проверьте актуальный предпросмотр.",
  lead_confirmation_required: "Сначала отдельно подтвердите состав черновика.",
  lead_idempotency_conflict:
    "Для этого черновика уже создана квитанция либо ключ повторного запроса относится к другому действию. Обновите историю.",
  lead_product_unavailable:
    "Выбранный продукт отсутствует или устарел. Обновите каталог и состав заявки.",
  lead_not_found: "Заявка не найдена или недоступна в этой гостевой сессии.",
  lead_already_submitted:
    "Этот демо-черновик уже завершён. Квитанция доступна в истории.",
  bank_catalogue_unavailable:
    "Каталог временно недоступен или не прошёл проверку. Предложения не подставляются автоматически.",
  bank_catalogue_version_conflict:
    "Каталог обновился. Проверьте актуальные сведения и повторите подбор.",
  version_conflict:
    "Профиль изменён другим запросом. Загружена актуальная версия; проверьте данные и повторите действие.",
  profile_incomplete:
    "Заполните обязательные поля профиля перед подтверждением.",
  conversation_not_found:
    "Беседа не найдена или гостевой доступ утрачен. Можно начать новую беседу.",
};
export async function request<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    credential?: Credential;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  if (!path.startsWith("/api/v1/") && path !== "/healthz")
    throw new Error("Unsupported API path");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  // Guest keys only go to same-origin conversation routes; never URLs or logs.
  if (
    options.credential &&
    path.startsWith(`/api/v1/conversations/${options.credential.id}`)
  )
    headers["X-Conversation-Token"] = options.credential.token;
  try {
    const response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(190_000)])
        : AbortSignal.timeout(190_000),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const code =
        typeof payload?.detail?.code === "string"
          ? payload.detail.code
          : `http_${response.status}`;
      const message =
        messages[code] ||
        (response.status === 422
          ? "Проверьте вводные: сервер отклонил значения. Денежные суммы — неотрицательные, чек > 0, доля затрат < 1."
          : response.status >= 502
            ? "Сервис временно недоступен. Если ошибка возникла в чате, проверьте Ollama и загруженную модель."
            : `Не удалось выполнить запрос (${response.status}).`);
      throw new ApiError(response.status, code, message);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError || options.signal?.aborted) throw error;
    throw new ApiError(
      0,
      "network",
      "Нет ответа от сервиса или превышено время ожидания. Обновите беседу перед повторной отправкой.",
    );
  }
}
export async function history(credential: Credential, signal?: AbortSignal) {
  const result: Schemas["MessageView"][] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await request<Schemas["MessageView"][]>(
      `/api/v1/conversations/${credential.id}/messages?limit=100&offset=${offset}`,
      { credential, signal },
    );
    result.push(...page);
    if (page.length < 100) return result;
  }
}
export const rub = (value: string | number | null | undefined) =>
  value == null
    ? "Нет данных"
    : new Intl.NumberFormat("ru-RU", {
        style: "currency",
        currency: "RUB",
        maximumFractionDigits: 0,
      }).format(Number(value));
export const date = (value: string) =>
  new Date(value).toLocaleDateString("ru-RU");
export const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Не удалось выполнить действие.";
