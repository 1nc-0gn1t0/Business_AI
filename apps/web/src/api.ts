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
  database_unavailable:
    "База данных временно недоступна. Повторите действие после восстановления сервиса.",
  llm_timeout:
    "Ollama превысила время ожидания. Текст сохранён, повторите запрос.",
  llm_queue_full:
    "Очередь локальной модели заполнена. Дождитесь завершения текущего диалога и повторите сообщение.",
  llm_queue_timeout:
    "Время ожидания локальной модели истекло. Текст сохранён, повторите сообщение позже.",
  request_cancelled: "Запрос отменён. Обновите беседу перед повторной отправкой.",
  llm_invalid_response:
    "Ответ локальной модели не прошёл проверку. Текст сохранён, повторите запрос или исправьте профиль вручную.",
  report_outdated:
    "Профиль или источники изменились. Обновите отчёт перед скачиванием.",
  report_results_changed:
    "Результаты анализа изменились. Повторите расчёты и подготовьте отчёт заново.",
  report_profile_mismatch:
    "Результаты относятся к другой версии профиля. Повторите расчёты.",
  report_no_analysis:
    "Для отчёта нужен хотя бы геоанализ или финансовый расчёт.",
  report_profile_not_confirmed: "Сначала подтвердите бизнес-профиль.",
  report_geo_version_or_limit:
    "Повторите геоанализ с фиксированной версией данных и не более пяти зон.",
  report_invalid_zone:
    "Выбранная зона не соответствует результатам анализа. Выберите её заново.",
  report_invalid_walking_context:
    "Повторите пешеходный анализ на той же версии геоданных.",
  report_request_too_large:
    "Объём вводных отчёта превышает допустимый размер. Сократите вводные.",
  request_body_too_large:
    "Запрос слишком велик. Сократите текст или количество вводных.",
  request_structure_too_large:
    "Слишком много вложенных данных или элементов. Сократите вводные.",
  invalid_request_structure:
    "Проверьте формат вводных: сервер отклонил структуру запроса.",
  request_text_too_long:
    "Текст слишком длинный. Сократите сообщение или вводные.",
  request_body_timeout:
    "Передача запроса заняла слишком много времени. Проверьте соединение.",
  request_target_too_large:
    "Адрес запроса слишком длинный. Сократите параметры.",
  request_headers_too_large: "Слишком большой объём заголовков запроса.",
  request_capacity_busy:
    "Сервис занят. Дождитесь завершения текущих операций и повторите действие.",
  request_rate_limited:
    "Превышен временный лимит запросов. Повторите действие позже.",
  resource_quota_exceeded:
    "Достигнут лимит сохраняемых данных. Обратитесь к владельцу локального сервиса; повтор запроса не сбросит квоту.",
  report_snapshot_too_large:
    "Снимок отчёта слишком велик. Уменьшите область пешеходного анализа.",
  report_pdf_too_large:
    "PDF превышает допустимый размер. Уменьшите объём анализа.",
  report_render_limit:
    "Текст или таблицы превышают ограничения вёрстки. Сократите длинные вводные.",
  report_not_found: "Отчёт не найден или недоступен в этой гостевой сессии.",
  report_integrity_error:
    "Снимок отчёта не прошёл проверку целостности. Подготовьте новый отчёт.",
  report_limit_reached:
    "Достигнут лимит отчётов для беседы. Сохранённые отчёты остаются доступны.",
  report_generation_timeout:
    "Подготовка отчёта превысила лимит времени. Уменьшите объём анализа.",
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
async function responseError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  const code =
    typeof payload?.detail?.code === "string"
      ? payload.detail.code
      : `http_${response.status}`;
  let message =
    messages[code] ||
    (response.status === 422
      ? "Проверьте вводные: сервер отклонил значения. Проверьте длину текста, бюджет и допустимые диапазоны чисел."
      : response.status >= 502
        ? "Сервис временно недоступен. Если ошибка возникла в чате, проверьте Ollama и загруженную модель."
        : `Не удалось выполнить запрос (${response.status}).`);
  const retry = response.headers.get("Retry-After");
  if (response.status === 429 && retry && /^\d{1,6}$/.test(retry))
    message += ` Повторная попытка возможна через ${Number(retry)} с.`;
  return new ApiError(response.status, code, message);
}
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
        ? AbortSignal.any([options.signal, AbortSignal.timeout(250_000)])
        : AbortSignal.timeout(250_000),
    });
    if (!response.ok) {
      throw await responseError(response);
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

export async function requestFile(
  path: string,
  credential: Credential,
  signal?: AbortSignal,
): Promise<Blob> {
  if (!path.startsWith(`/api/v1/conversations/${credential.id}/reports/`))
    throw new Error("Unsupported download path");
  const response = await fetch(path, {
    headers: { "X-Conversation-Token": credential.token },
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(30_000)])
      : AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.blob();
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
