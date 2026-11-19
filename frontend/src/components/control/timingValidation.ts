/** B5 前端配时表单校验；后端 Pydantic / TimingService 仍是最终权威校验。 */
import type { TimingConfig } from "../../types/signal";

export type TimingField = keyof TimingConfig;

const MOVEMENTS: Array<{
  label: string;
  green: TimingField;
  yellow: TimingField;
}> = [
  { label: "南北左转", green: "ns_left_green", yellow: "ns_left_yellow" },
  { label: "南北直行", green: "ns_straight_green", yellow: "ns_straight_yellow" },
  { label: "东西左转", green: "ew_left_green", yellow: "ew_left_yellow" },
  { label: "东西直行", green: "ew_straight_green", yellow: "ew_straight_yellow" },
];

export function getTimingValidationErrors(value: TimingConfig): string[] {
  const errors: string[] = [];
  const values = Object.entries(value) as Array<[TimingField, number]>;

  for (const [field, duration] of values) {
    if (!Number.isFinite(duration)) {
      errors.push(`${field} 必须是有效数字。`);
    }
  }

  for (const movement of MOVEMENTS) {
    const green = value[movement.green];
    const yellow = value[movement.yellow];
    if (!Number.isFinite(green) || green <= 8) {
      errors.push(`${movement.label}绿灯必须大于 8 秒。`);
    }
    if (!Number.isFinite(yellow) || yellow <= 0) {
      errors.push(`${movement.label}黄灯必须大于 0 秒。`);
    }
  }

  if (errors.length > 0) return errors;

  const cycle = values.reduce((sum, [, duration]) => sum + duration, 0);
  for (const movement of MOVEMENTS) {
    const red = cycle - value[movement.green] - value[movement.yellow];
    if (red <= 10) {
      errors.push(`${movement.label}计算红灯为 ${red.toFixed(2)} 秒，必须大于 10 秒。`);
    }
  }
  return errors;
}
