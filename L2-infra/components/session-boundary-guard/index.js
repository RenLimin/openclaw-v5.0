import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { decide, audit } from "./core.js";

/**
 * session-boundary-guard — 会话边界护栏（插件注册入口）
 *
 * 机制性拦截 agent 将消息/任务注入 pinned/live 会话（agent:main:dashboard:*）
 * 的跨会话调用，杜绝串台事故（FB-20261103-03）复发。
 * 纯逻辑见 core.js（零依赖，可单测）。
 */

export default definePluginEntry({
  id: "session-boundary-guard",
  name: "Session Boundary Guard",
  description: "机制性拦截 agent 向 pinned/live 会话（dashboard:*）注入消息/任务（FB-20261103-03）",
  register(api) {
    api.on(
      "before_tool_call",
      (event, ctx) => {
        const config = {
          mode: "approve",
          allowTargets: [],
          debug: false,
          ...(api.pluginConfig ?? {}),
        };
        const source = ctx?.sessionKey ?? "(unknown)";
        const decision = decide(event, config, source);
        if (decision === undefined && config.debug === true) {
          const target =
            typeof event?.params?.sessionKey === "string"
              ? event.params.sessionKey
              : event?.params?.visible === true
                ? "(visible-spawn)"
                : "(n/a)";
          audit(source, event?.toolName ?? "(unknown)", target, "allowed", config.mode);
        }
        return decision;
      },
      { matcher: ["sessions_send", "sessions_spawn"], priority: 50 },
    );
  },
});
