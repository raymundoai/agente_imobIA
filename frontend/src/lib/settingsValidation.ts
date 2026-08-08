export const KNOWLEDGE_MAX_BYTES = 10 * 1024 * 1024;
export const KNOWLEDGE_ACCEPT = ".txt,.md,.markdown,.pdf,.docx";

export type UserFormValidation = Partial<Record<"name" | "email" | "password", string>>;

export function validateNewUserForm(form: {
  name: string;
  email: string;
  password: string;
}): UserFormValidation {
  const errors: UserFormValidation = {};
  if (form.name.trim().length < 2) errors.name = "Informe pelo menos 2 caracteres.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
    errors.email = "Informe um email válido.";
  }
  if (form.password.length < 12) errors.password = "Use pelo menos 12 caracteres.";
  return errors;
}

export function validateKnowledgeFile(file: Pick<File, "name" | "size">): string | null {
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (![".txt", ".md", ".markdown", ".pdf", ".docx"].includes(extension)) {
    return "Use um arquivo TXT, Markdown, PDF ou DOCX.";
  }
  if (file.size > KNOWLEDGE_MAX_BYTES) return "O arquivo deve ter no máximo 10 MB.";
  if (file.size === 0) return "O arquivo selecionado está vazio.";
  return null;
}

export function isValidBrazilianDocument(value: string, type: "cpf" | "cnpj"): boolean {
  const digits = value.replace(/\D/g, "");
  if (digits.length !== (type === "cpf" ? 11 : 14) || /^(\d)\1+$/.test(digits)) return false;
  return type === "cpf" ? validateCpf(digits) : validateCnpj(digits);
}

function validateCpf(digits: string): boolean {
  const check = (length: number) => {
    const sum = digits.slice(0, length).split("").reduce(
      (total, digit, index) => total + Number(digit) * (length + 1 - index),
      0,
    );
    const remainder = (sum * 10) % 11;
    return (remainder === 10 ? 0 : remainder) === Number(digits[length]);
  };
  return check(9) && check(10);
}

function validateCnpj(digits: string): boolean {
  const calculate = (length: 12 | 13) => {
    const weights = length === 12
      ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
      : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    const sum = digits.slice(0, length).split("").reduce(
      (total, digit, index) => total + Number(digit) * weights[index],
      0,
    );
    const remainder = sum % 11;
    return (remainder < 2 ? 0 : 11 - remainder) === Number(digits[length]);
  };
  return calculate(12) && calculate(13);
}
