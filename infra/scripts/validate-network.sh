#!/bin/bash
# ============================================
# VNet and Networking Validation
# Validates VNet, subnets, and NSG configuration
# ============================================

set -e

RESOURCE_GROUP="${1:-rg-rag-indexing-lab-swc}"
VNET_NAME="${2:-vnet-ragi-*}"

echo "=== VNet and Networking Validation ==="
echo "Resource Group: $RESOURCE_GROUP"
echo ""

# Check VNet exists
echo "Checking VNet..."
VNET=$(az network vnet list -g "$RESOURCE_GROUP" --query "[0].name" -o tsv)
if [ -n "$VNET" ]; then
    echo "✓ VNet found: $VNET"
else
    echo "✗ VNet not found in $RESOURCE_GROUP"
    exit 1
fi

# Check subnets
echo ""
echo "Checking subnets..."
SUBNETS=$(az network vnet subnet list -g "$RESOURCE_GROUP" --vnet-name "$VNET" --query "[].name" -o tsv)
for subnet in $SUBNETS; do
    echo "✓ Subnet: $subnet"
done

# Check NSGs
echo ""
echo "Checking Network Security Groups..."
NSGS=$(az network nsg list -g "$RESOURCE_GROUP" --query "[].name" -o tsv)
if [ -n "$NSGS" ]; then
    echo "✓ NSGs found:"
    while IFS= read -r nsg; do
        echo "  - $nsg"
    done <<< "$NSGS"
else
    echo "⚠ No NSGs found"
fi

# Check Private Endpoints
echo ""
echo "Checking Private Endpoints..."
PES=$(az network private-endpoint list -g "$RESOURCE_GROUP" --query "[].name" -o tsv)
if [ -n "$PES" ]; then
    echo "✓ Private Endpoints found:"
    while IFS= read -r pe; do
        echo "  - $pe"
    done <<< "$PES"
else
    echo "⚠ No Private Endpoints found"
fi

# Check Private DNS Zones
echo ""
echo "Checking Private DNS Zones..."
PDNS=$(az network private-dns zone list -g "$RESOURCE_GROUP" --query "[].name" -o tsv)
if [ -n "$PDNS" ]; then
    echo "✓ Private DNS Zones found:"
    while IFS= read -r pdns; do
        echo "  - $pdns"
    done <<< "$PDNS"
else
    echo "⚠ No Private DNS Zones found"
fi

echo ""
echo "✓ VNet and Networking validation complete"
