import { DOCS_NAV } from "@/lib/docs-nav";

interface DocsSidebarProps {
  active: string;
  open: boolean;
  onNav: () => void;
}

export function DocsSidebar({ active, open, onNav }: DocsSidebarProps) {
  return (
    <aside className={"docs-side" + (open ? " open" : "")}>
      {DOCS_NAV.map((grp) => (
        <div className="docs-side-group" key={grp.group}>
          <h4>{grp.group}</h4>
          {grp.items.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              className={active === item.id ? "active" : ""}
              onClick={onNav}
            >
              {item.label}
            </a>
          ))}
        </div>
      ))}
    </aside>
  );
}
