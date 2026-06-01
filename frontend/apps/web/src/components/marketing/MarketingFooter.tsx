import { Phone, Mail, Clock, MessageCircle, Video, Globe, Send } from "lucide-react";
import { BrandLockup } from "@/components/brand/SealLogo";
import { FOOTER } from "@/lib/marketing";

const SOCIAL = [MessageCircle, Video, Globe, Send];

export function MarketingFooter() {
  return (
    <footer id="footer" className="relative overflow-hidden border-t border-border bg-paper pt-2">
      {/* 底部远山薄雾 */}
      <img
        src="/assets/ink/divider.webp"
        alt=""
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-24 w-full object-cover opacity-30 mix-blend-multiply"
      />

      <div className="relative mx-auto max-w-7xl px-6 py-14">
        <div className="grid gap-10 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_1.6fr]">
          {/* brand */}
          <div>
            <BrandLockup size={36} />
            <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {FOOTER.intro}
            </p>
            <div className="mt-5 flex gap-2.5">
              {SOCIAL.map((Icon, i) => (
                <span
                  key={i}
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-muted-foreground transition-colors hover:border-brand/30 hover:text-brand"
                >
                  <Icon className="h-4 w-4" />
                </span>
              ))}
            </div>
          </div>

          {/* link columns */}
          {FOOTER.columns.map((col) => (
            <div key={col.title}>
              <h4 className="text-sm font-semibold text-ink">{col.title}</h4>
              <ul className="mt-4 space-y-2.5">
                {col.links.map((l) => (
                  <li key={l}>
                    <span className="cursor-pointer text-sm text-muted-foreground transition-colors hover:text-brand">
                      {l}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* contact */}
          <div>
            <h4 className="text-sm font-semibold text-ink">联系我们</h4>
            <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
              <li className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted" />
                {FOOTER.contact.hours}
              </li>
              <li className="flex items-center gap-2">
                <Phone className="h-4 w-4 text-muted" />
                <span className="font-display text-base font-bold text-ink">
                  {FOOTER.contact.phone}
                </span>
              </li>
              <li className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-muted" />
                {FOOTER.contact.email}
              </li>
            </ul>
          </div>
        </div>

        <div className="ink-rule my-9" />

        <div className="flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-xs text-muted">
          {[FOOTER.copyright, ...FOOTER.icp.split(/\s*·\s*/)].flatMap((part, i) =>
            i === 0
              ? [<span key={i}>{part}</span>]
              : [
                  <span key={`sep-${i}`} aria-hidden className="text-muted/40">
                    ·
                  </span>,
                  <span key={i}>{part}</span>,
                ],
          )}
        </div>
      </div>
    </footer>
  );
}
