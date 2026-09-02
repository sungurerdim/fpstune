def edit(p, pairs):
    s = open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (p, old[:70])
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8", newline="").write(s)


edit(
    "src/components/HomeTab.tsx",
    [
        (
            """                <p className="text-xs text-muted-foreground mt-0.5">
                  {s.detectionError
                    ? t("home.advisoryUnreadReason", { reason: s.detectionError })
                    : t("home.advisoryUnreadNoReason")}
                </p>""",
            """                <p className="text-xs text-muted-foreground mt-0.5">
                  {s.detectionError
                    ? t("home.advisoryUnreadReason", { reason: s.detectionError })
                    : isAdmin === false
                      ? t("home.advisoryUnreadNeedsAdmin")
                      : t("home.advisoryUnreadNoReason")}
                </p>""",
        ),
        (
            """  const { data: systemInfo } = useQuery({""",
            """  // Several checks read data Windows only hands to an elevated caller — the
  // ACPI thermal class returns nothing at all otherwise. When a check read
  // nothing and fpstune is not elevated, that is the likeliest reason and the
  // one the user can act on, so the row says it instead of leaving the space
  // blank. Stated as the likely cause, never as a certainty.
  const isAdmin = useQuery({
    queryKey: ["system"],
    queryFn: api.getSystemInfo,
    staleTime: Infinity,
  }).data?.is_admin;

  const { data: systemInfo } = useQuery({""",
        ),
    ],
)

edit(
    "src/i18n/en.ts",
    [
        (
            """  "home.advisoryUnreadNoReason":
""",
            """  "home.advisoryUnreadNeedsAdmin":
    "Nothing was read. fpstune is not running as Administrator, which several checks need.",
  "home.advisoryUnreadNoReason":
""",
        )
    ],
)

edit(
    "src/i18n/tr.ts",
    [
        (
            """  "home.advisoryUnreadNoReason":
""",
            """  "home.advisoryUnreadNeedsAdmin":
    "Hiçbir değer okunamadı. fpstune yönetici olarak çalışmıyor; birkaç denetim bunu gerektiriyor.",
  "home.advisoryUnreadNoReason":
""",
        )
    ],
)
print("ok")
