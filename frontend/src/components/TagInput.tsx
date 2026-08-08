import { useState, type ClipboardEvent, type KeyboardEvent } from "react";

const SYSTEM_CONTACT_TAGS = new Set([
  "manual",
  "qualification",
  "telegram",
  "whatsapp",
  "whatsapp-owner",
]);
const MAX_CONTACT_TAGS = 50;

export function isSystemContactTag(tag: string) {
  return SYSTEM_CONTACT_TAGS.has(tag.trim().toLowerCase());
}

export function userContactTags(tags: string[]) {
  return tags.filter((tag) => !isSystemContactTag(tag));
}

export function mergeUserContactTags(current: string[], userTags: string[]) {
  const systemTags = current.filter(isSystemContactTag);
  const availableUserSlots = Math.max(0, MAX_CONTACT_TAGS - systemTags.length);
  return [
    ...systemTags,
    ...userTags.filter((tag) => !isSystemContactTag(tag)).slice(0, availableUserSlots),
  ];
}

export function TagInput({
  tags,
  onChange,
  placeholder = "Digite e pressione Enter ou espaço",
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  function add(values: string[]) {
    const next = [...tags];
    for (const raw of values) {
      const value = raw.trim();
      if (!value || isSystemContactTag(value)) continue;
      if (next.some((tag) => tag.toLocaleLowerCase("pt-BR") === value.toLocaleLowerCase("pt-BR"))) {
        continue;
      }
      next.push(value);
    }
    onChange(next.slice(0, MAX_CONTACT_TAGS));
    setDraft("");
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (["Enter", " ", ","].includes(event.key)) {
      event.preventDefault();
      add([draft]);
      return;
    }
    if (event.key === "Backspace" && !draft && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const values = event.clipboardData.getData("text").split(/[\s,]+/);
    if (values.length <= 1) return;
    event.preventDefault();
    add(values);
  }

  return (
    <div className="tag-input" onClick={(event) => event.currentTarget.querySelector("input")?.focus()}>
      {tags.map((tag) => (
        <span className="tag-capsule" key={tag}>
          {tag}
          <button
            aria-label={`Remover tag ${tag}`}
            onClick={(event) => {
              event.stopPropagation();
              onChange(tags.filter((item) => item !== tag));
            }}
            type="button"
          >
            ×
          </button>
        </span>
      ))}
      <input
        aria-label="Adicionar tag"
        onBlur={() => add([draft])}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        placeholder={tags.length === 0 ? placeholder : "Adicionar tag"}
        value={draft}
      />
    </div>
  );
}
