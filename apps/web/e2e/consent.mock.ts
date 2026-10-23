import type { Page } from "@playwright/test";
import type { Schemas } from "../src/api";
import fixture from "../../../docs/examples/BA-012-consents.json" with { type: "json" };

// Offline adapter only. Real E2E never imports or registers these routes.
export async function mockConsents(page: Page) {
  const state = structuredClone(fixture) as Schemas["ConsentState"];
  const assistant = state.consents.find((c) => c.purpose === "assistant")!;
  Object.assign(assistant, { status: "granted", revision: 1 });
  await page.route("**/api/v1/consent-texts", (route) =>
    route.fulfill({ json: state.texts }),
  );
  await page.route(
    /\/api\/v1\/conversations\/[^/]+\/consents(?:\/[^/?]+)?$/,
    (route) => {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON();
        const purpose = new URL(route.request().url()).pathname
          .split("/")
          .pop();
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
      }
      return route.fulfill({ json: state });
    },
  );
  await page.route(/\/api\/v1\/conversations\/[^/]+\/leads$/, (route) =>
    route.fulfill({ json: { drafts: [], receipts: [] } }),
  );
}
