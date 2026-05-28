import { larisaIvanovnaConfig } from "../config";

export interface TelegramMessage {
  chatId: string;
  text: string;
  parseMode?: "Markdown" | "HTML";
  disableWebPagePreview?: boolean;
}

export interface TelegramSendResult {
  delivered: boolean;
  routeKey: string;
  limitation?: string;
}

export interface TelegramRouteBridge {
  routeKey: string;
  send(message: TelegramMessage): Promise<TelegramSendResult>;
}

export interface TelegramProvider {
  readonly routeKey: string;
  readonly providerId?: string;
  send(message: TelegramMessage): Promise<TelegramSendResult>;
}

export class ExistingTelegramRouteProvider implements TelegramProvider {
  readonly routeKey: string;
  readonly providerId = "existing-telegram-route";
  private readonly route: TelegramRouteBridge;

  constructor(route: TelegramRouteBridge) {
    this.route = route;
    this.routeKey = route.routeKey;
  }

  async send(message: TelegramMessage): Promise<TelegramSendResult> {
    return this.route.send(message);
  }
}

export class NullTelegramProvider implements TelegramProvider {
  readonly providerId = "null-telegram";
  readonly routeKey: string;

  constructor(routeKey = larisaIvanovnaConfig.telegram.routeKey) {
    this.routeKey = routeKey;
  }

  async send(): Promise<TelegramSendResult> {
    return {
      delivered: false,
      routeKey: this.routeKey,
      limitation:
        "Telegram routing для Ларисы Ивановны должен быть передан из существующего shared-контура.",
    };
  }
}
