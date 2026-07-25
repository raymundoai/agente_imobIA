export function jobsUnavailableAlert(status?: number) {
  return status === 403
    ? "Seu perfil não permite verificar a fila de atendimentos; solicite a um gestor."
    : "Não foi possível verificar a fila de atendimentos.";
}
