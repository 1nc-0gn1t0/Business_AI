import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LeadFlow from "./LeadFlow";
import type { Conversation, Schemas } from "./api";
import bank from "../../../docs/examples/BA-011-coffee.json";
import consentFixture from "../../../docs/examples/BA-012-consents.json";

const catalogue = bank.response.catalogue as Schemas["CatalogueView"];
const conversation: Conversation = {
  id: bank.response.profile_snapshot.conversation_id,
  version: 2,
  profile: bank.response.profile_snapshot as Conversation["profile"],
  state: "confirmed",
  missing_fields: [],
  assistant_message: "",
  extraction_mode: "stub",
  created_at: "2026-10-23T00:00:00Z",
  updated_at: "2026-10-23T00:00:00Z",
};
const credential = { id: conversation.id, token: "explicit-mock-key-only" };
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });

function mockApi(options: { stale?: boolean; failSubmit?: boolean } = {}) {
  const state = structuredClone(consentFixture) as Schemas["ConsentState"];
  state.consents[0] = { ...state.consents[0], status: "granted", revision: 1 };
  let draft: Schemas["LeadDraft"] | null = null;
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (path, init) => {
      const url = String(path);
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      if (url.endsWith("/consents")) return json(state);
      if (url.endsWith("/leads")) return json({ drafts: [], receipts: [] });
      if (url.includes("/consents/")) {
        const purpose = url.split("/").pop();
        state.consents = state.consents.map((c) =>
          c.purpose === purpose
            ? {
                ...c,
                revision: c.revision + 1,
                status:
                  body.decision === "grant"
                    ? "granted"
                    : body.decision === "withdraw"
                      ? "withdrawn"
                      : "declined",
              }
            : c,
        );
        return json(state);
      }
      if (url.endsWith("/submit")) {
        if (options.failSubmit)
          return json({ detail: { code: "lead_profile_stale" } }, 409);
        return json({
          id: "local-receipt",
          draft_id: draft!.id,
          draft_revision: draft!.revision,
          profile_version: 2,
          payload: draft!.payload,
          payload_fingerprint: draft!.payload_fingerprint,
          consents: state.consents.filter((c) => c.status === "granted"),
          created_at: conversation.created_at,
          status: "demo_created",
          sent_to_bank: false,
          message:
            "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
        });
      }
      if (url.endsWith("/confirm")) {
        draft = { ...draft!, state: "confirmed" };
        return json(draft);
      }
      draft = {
        id: "draft-test",
        revision: draft ? draft.revision + 1 : 1,
        profile_version: 2,
        profile_snapshot: conversation.profile,
        consents: state.consents.filter((c) => c.status === "granted"),
        payload: {
          mode: "demonstration",
          recipient: "local_mock_only",
          fields: body.fields,
          products: catalogue.products.filter((p) =>
            body.product_ids.includes(p.product.id),
          ),
          catalogue_version: catalogue.version,
          catalogue_fingerprint: catalogue.fingerprint,
          field_origins: {},
        },
        payload_fingerprint: "a".repeat(64),
        state: "draft",
        stale: options.stale || false,
        created_at: conversation.created_at,
        updated_at: conversation.created_at,
      };
      return json(draft, 201);
    });
  render(
    <LeadFlow
      conversation={conversation}
      credential={credential}
      catalogue={catalogue}
      active
    />,
  );
  return fetch;
}

async function prepare() {
  await screen.findByText("1. Интересующие продукты");
  fireEvent.click(screen.getByRole("checkbox", { name: /Расчётно-кассовое/ }));
  fireEvent.click(
    screen.getByRole("button", {
      name: "Согласиться: Подготовка и демонстрационная передача",
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Подготовить демо-черновик →" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Подготовить демо-черновик →" }),
  );
  await screen.findByLabelText("Предпросмотр заявки");
}
async function confirm() {
  fireEvent.click(
    screen.getByLabelText("Я проверил все поля и выбранные продукты"),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: "Подтвердить состав заявки",
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByLabelText(
        "Подтверждаю создание демонстрационной заявки без отправки в банк",
      ),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByLabelText(
      "Подтверждаю создание демонстрационной заявки без отправки в банк",
    ),
  );
}

describe("consent and demo lead with explicit offline adapter", () => {
  it("requires separate consent and preserves marketing refusal", async () => {
    mockApi();
    await screen.findByText("1. Интересующие продукты");
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Расчётно-кассовое/ }),
    );
    expect(
      screen.getByRole("button", { name: "Подготовить демо-черновик →" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Отказаться: Маркетинговые рекомендации",
      }),
    );
    await screen.findByText("Отказ", { exact: true });
    expect(
      screen.getByRole("button", { name: "Подготовить демо-черновик →" }),
    ).toBeDisabled();
    expect(screen.getByText(/Отказ от маркетинга не блокирует/)).toBeVisible();
  });
  it("previews editable payload, requires confirmations and shows local receipt", async () => {
    const fetch = mockApi();
    await prepare();
    await confirm();
    fireEvent.click(
      screen.getByRole("button", { name: "Создать демонстрационную заявку →" }),
    );
    await screen.findByRole("heading", {
      name: "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
    });
    const call = fetch.mock.calls.find(([path]) =>
      String(path).endsWith("/submit"),
    )!;
    expect(String(call[0])).not.toContain(credential.token);
    expect(call[1]?.headers).toHaveProperty(
      "X-Conversation-Token",
      credential.token,
    );
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({
      confirmed: true,
      expected_revision: 1,
      payload_fingerprint: "a".repeat(64),
    });
  });
  it("removes optional budget and blocks submission until edited draft is saved and confirmed", async () => {
    mockApi();
    await prepare();
    await confirm();
    fireEvent.change(screen.getByLabelText("Бюджет заявки"), {
      target: { value: "" },
    });
    expect(
      screen.getByRole("button", { name: "Создать демонстрационную заявку →" }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Сохранить новую версию черновика" }),
    );
    await waitFor(() => expect(screen.getByText("v2 · draft")).toBeVisible());
    expect(
      screen.getByLabelText("Я проверил все поля и выбранные продукты"),
    ).not.toBeChecked();
  });
  it("withdrawal blocks confirmed draft and stale server rejection creates no receipt", async () => {
    mockApi({ failSubmit: true });
    await prepare();
    await confirm();
    fireEvent.click(
      screen.getByRole("button", { name: "Создать демонстрационную заявку →" }),
    );
    await screen.findByRole("alert");
    expect(screen.queryByLabelText("Демо-квитанция")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Отозвать: Подготовка и демонстрационная передача",
      }),
    );
    await screen.findByText("Отозвано", { exact: true });
    expect(
      screen.getByRole("button", { name: "Создать демонстрационную заявку →" }),
    ).toBeDisabled();
  });
  it("reports unavailable API without fabricating consent or a draft", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ detail: { code: "unavailable" } }, 503),
    );
    render(
      <LeadFlow
        conversation={conversation}
        credential={credential}
        catalogue={catalogue}
        active
      />,
    );
    await screen.findByRole("alert");
    expect(
      screen.queryByLabelText("Предпросмотр заявки"),
    ).not.toBeInTheDocument();
  });
});
