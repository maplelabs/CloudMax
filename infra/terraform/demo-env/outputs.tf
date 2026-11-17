output "vm_id" {
  description = "Resource ID of the demo VM."
  value       = azurerm_linux_virtual_machine.demo.id
}

output "public_ip_address" {
  description = "Static public IP address of the demo environment."
  value       = azurerm_public_ip.demo.ip_address
}

output "os_disk_id" {
  description = "Resource ID of the OS managed disk (source for the next snapshot cycle)."
  value       = azurerm_managed_disk.os.id
}

output "data_disk_id" {
  description = "Resource ID of the data managed disk (source for the next snapshot cycle)."
  value       = azurerm_managed_disk.data.id
}

output "vm_principal_id" {
  description = "Principal (object) ID of the VM's system-assigned managed identity."
  value       = azurerm_linux_virtual_machine.demo.identity[0].principal_id
}
