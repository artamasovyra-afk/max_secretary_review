import { request } from "./client";
import type { Organization } from "../types/organization";

export function getOrganizations(): Promise<Organization[]> {
  return request<Organization[]>("/organizations");
}

export function getOrganization(organizationId: string): Promise<Organization> {
  return request<Organization>(`/organizations/${organizationId}`);
}

export const listOrganizations = getOrganizations;
