import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LibraryWorkspace } from "./LibraryWorkspace";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(),
}));

const completedJob = {
  id: "img_stored",
  status: "completed",
  progress: 100,
  phase: "completed",
  currentStep: 8,
  totalSteps: 8,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A precise persistent studio image",
  tags: [],
  settings: {
    aspectRatio: "4:3",
    style: "editorial",
    seed: 42,
    provider: "demo",
    operation: "generate",
    hasFaceReference: false,
    sourceJobId: null,
    edit: null,
  },
  createdAt: "2026-08-01T00:00:00Z",
  startedAt: "2026-08-01T00:00:01Z",
  completedAt: "2026-08-01T00:00:04Z",
  result: {
    url: "/api/v1/image-jobs/img_stored/result",
    thumbnailUrl: "/api/v1/image-jobs/img_stored/thumbnail",
    mimeType: "image/svg+xml",
    width: 960,
    height: 720,
    sizeBytes: 4096,
    sha256: "a".repeat(64),
    available: true,
  },
  error: null,
};

function renderLibrary() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return render(<LibraryWorkspace />, { wrapper: Wrapper });
}

describe("LibraryWorkspace", () => {
  beforeEach(() => navigation.replace.mockReset());

  it("shows completed persistent results", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: [completedJob] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    renderLibrary();

    expect(await screen.findByText(completedJob.prompt)).toBeInTheDocument();
    expect(screen.getByText("1 loaded")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: `Selected result for ${completedJob.prompt}` })).toHaveAttribute(
      "src",
      "http://localhost:8000/api/v1/image-jobs/img_stored/result",
    );
    expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute(
      "href",
      "/edit?sourceJobId=img_stored",
    );
  });

  it("offers a retry when the persistent index is unavailable", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderLibrary();
    await user.click(await screen.findByRole("button", { name: "Retry" }));

    expect(await screen.findByText("No stored images yet")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps stored results visible when a refresh temporarily fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [completedJob] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderLibrary();
    await screen.findByText(completedJob.prompt);
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Refresh failed");
    expect(screen.getByText(completedJob.prompt)).toBeInTheDocument();
    expect(screen.getByText("1 loaded")).toBeInTheDocument();
  });

  it("uses selection mode for batch deletion without opening another detail", async () => {
    let deleted = false;
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/tags")) {
        return Promise.resolve(new Response(JSON.stringify({ tags: [] }), { status: 200 }));
      }
      if (url.endsWith("/assets/delete") && init?.method === "POST") {
        deleted = true;
        return Promise.resolve(new Response(JSON.stringify({ deletedIds: [completedJob.id] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      }
      return Promise.resolve(new Response(JSON.stringify({ items: deleted ? [] : [completedJob] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderLibrary();

    await user.click(await screen.findByRole("checkbox", { name: /Select generate/ }));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete selected" }));
    await user.click(screen.getByRole("button", { name: "Confirm 1" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("No stored images yet")).toBeInTheDocument();
  });

  it("changes grid density and sends prompt search to the server", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      const payload = url.endsWith("/tags") ? { tags: [] } : { items: [completedJob] };
      return Promise.resolve(new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText(completedJob.prompt);

    const density = screen.getByRole("slider", { name: "Thumbnail size" });
    fireEvent.change(density, { target: { value: "4" } });
    expect(density.parentElement).toHaveAttribute("title", "4 columns");
    await user.type(screen.getByRole("searchbox", { name: "Search prompts" }), "daylight");

    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([input]) => String(input).includes("search=daylight"),
    )).toBe(true));
  });

  it("adds a durable tag and exposes it in the filter", async () => {
    let currentJob = { ...completedJob, tags: [] as string[] };
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/tags") && init?.method === "PATCH") {
        currentJob = { ...currentJob, tags: ["review"] };
        return new Response(JSON.stringify(currentJob), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/tags")) {
        return new Response(JSON.stringify({ tags: currentJob.tags }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ items: [currentJob] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderLibrary();
    await screen.findByText(completedJob.prompt);

    await user.type(screen.getByRole("textbox", { name: "New tag" }), "Review");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect((await screen.findAllByText("review")).length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByRole("option", { name: "review" })).toBeInTheDocument();
  });
});
