output "vm_id" {
  description = "Resource ID of the demo VM."
  value       = azapi_resource.demo_vm.id
}

output "public_ip_address" {
  description = "Static public IP address of the demo environment (either the pre-existing public_ip_name IP, or a freshly created per-demo one -- see variables.tf)."
  value       = local.public_ip_address
}

output "os_disk_id" {
  description = <<-EOT
    Resource ID of the OS managed disk, for the steady-state (snapshot-restore)
    path only -- null on a bootstrap create, where the VM provisions its own
    OS disk inline from the base image instead (see main.tf). The next
    destroy cycle's snapshot will be taken against the VM's actual OS disk
    regardless of which path created it.
  EOT
  value       = local.restore_from_snapshot ? azurerm_managed_disk.os[0].id : null
}

output "data_disk_id" {
  description = "Resource ID of the data managed disk (source for the next snapshot cycle)."
  value       = azurerm_managed_disk.data.id
}

output "vm_principal_id" {
  description = "Principal (object) ID of the VM's system-assigned managed identity."
  value       = azapi_resource.demo_vm.identity[0].principal_id
}
