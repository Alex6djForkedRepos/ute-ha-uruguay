/**
 * Demo CLI del cliente UTE TS.
 * Uso:  tsx demo.ts <documento> <password>
 */
import { UteClient } from "./src/index.js";

async function main() {
  const [, , doc, pwd] = process.argv;
  if (!doc || !pwd) {
    console.error("uso: tsx demo.ts <documento> <password>");
    process.exit(1);
  }
  const ute = new UteClient();
  await ute.bootstrap();
  await ute.login(doc, pwd);
  console.log("✓ login OK");

  for (const acc of await ute.accounts()) {
    console.log(`\n▶ Cuenta ${acc.accountId} — ${acc.address}`);
    const debt = await ute.totalDebt(acc.accountId);
    const bp = await ute.billingPeriodSummary(acc.accountId);
    console.log(`  Deuda: $${debt.toLocaleString("es-UY")}`);
    console.log(
      `  Período ${bp.initialDate} → ${bp.finalDate}: ${bp.currentConsumptionKwh.toFixed(1)} kWh / $${bp.currentSpendingUyu.toLocaleString("es-UY")}`,
    );

    for (const svc of await ute.services(acc.accountId)) {
      console.log(
        `  Suministro ${svc.servicePointId} (${svc.tariffDescription}) — ${svc.address}`,
      );
      console.log(
        `    Voltaje ${svc.voltage} | ${svc.serviceType} | Pot. punta ${svc.contractedPowerOnPeak} kW | AMI ${svc.amiPresent} (${svc.amiType ?? "-"})`,
      );
      const today = new Date();
      const start = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
      const end = today.toISOString().slice(0, 10);
      const tous = await ute.consumptionByTou(
        svc.servicePointId,
        "TRIPLERES17",
        start,
        end,
      );
      const total = tous.reduce((a, t) => a + t.consumption, 0);
      console.log(`    Consumo ${start}–${end}: ${total.toFixed(1)} kWh`);
      for (const t of tous)
        console.log(`      ${t.tou.padEnd(6)} ${t.consumption.toFixed(1)} ${t.uom}`);
    }
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
