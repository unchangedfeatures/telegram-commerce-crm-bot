# 🚚 Delivery Feature - Quick Reference

## Key Changes Summary

### ⚙️ Delivery Parameters (Current)
| Parameter | Value | Notes |
|-----------|-------|-------|
| **Free Shipping Threshold** | 3 items | When order has ≥3 items, shipping is FREE |
| **Standard Delivery Cost** | 2.0€ | Applied when items < threshold |
| **Pickup Location** | AKROPOLIS | Always FREE |
| **Pickup Enabled** | YES | Customers can select pickup option |

### 📱 Bot Changes

**Address Selection Screen (NEW)**
```
User sees 4 buttons:
1. 📍 Отправить геолокацию (Send location via GPS)
2. 🏠 Ввести адрес текстом (Enter address manually)
3. 🏪 Самовывоз (AKROPOLIS) - БЕСПЛАТНО (Pickup - FREE)
4. 🔙 Назад к телефону (Back to phone)
```

**Delivery Cost Calculation**
```python
total_items = 3
→ FREE delivery (or pickup)

total_items = 2
→ 2€ delivery (or FREE pickup)

delivery_type = "pickup"
→ Always 0€ (FREE)
```

### 🎛️ Admin Panel Route
```
URL: http://your-server:5000/delivery-settings
Menu: Sidebar → 🚚 Доставка
Features:
  - View current settings
  - Update threshold and cost
  - Changes apply immediately
```

### 📝 Code Locations

| File | Changes | Lines |
|------|---------|-------|
| **orderHandlers.py** | Delivery logic, pickup handler | 314, 373, 448, 575, 995, 615-640, 820-835, 880-900 |
| **database/database.py** | Settings functions, defaults | 786-859 |
| **admin_app.py** | Routes & views | 800-843 |
| **templates/delivery_settings.html** | NEW form template | N/A |
| **templates/base.html** | Added navbar link | 280-285 |

### 🔄 User Journey (Checkout)

```
1. Cart Review
   ↓
2. Select Promo Code (optional)
   ↓
3. Enter Phone Number
   ↓
4. SELECT DELIVERY METHOD ← NEW
   ├─ 📍 Geolocation (auto-address detection)
   ├─ 🏠 Manual Address
   └─ 🏪 Pickup at AKROPOLIS (FREE)
   ↓
5. Order Summary & Confirmation
   ↓
6. Place Order
```

### 💰 Pricing Examples

**Order with 3 items (≥ threshold)**
```
Item 1: 5€
Item 2: 3€
Item 3: 4€
Subtotal: 12€
Delivery: FREE ✅
TOTAL: 12€
```

**Order with 2 items (< threshold)**
```
Item 1: 5€
Item 2: 3€
Subtotal: 8€
Delivery: 2€
TOTAL: 10€
OR
Delivery (Pickup): FREE ✅
TOTAL: 8€
```

### 🚀 Deployment Steps

1. **Backup current version**
   ```bash
   git commit -m "backup before deployment"
   git push origin main
   ```

2. **Push code to server**
   ```bash
   git pull  # on server
   ```

3. **Create delivery_settings table (if needed)**
   ```sql
   CREATE TABLE IF NOT EXISTS delivery_settings (
       id SERIAL PRIMARY KEY,
       free_delivery_threshold INT DEFAULT 3,
       standard_delivery_cost DECIMAL(10, 2) DEFAULT 2.0,
       high_demand_delivery_cost DECIMAL(10, 2) DEFAULT 2.0,
       high_demand_orders_threshold INT DEFAULT 7,
       pickup_location_name VARCHAR(255) DEFAULT 'AKROPOLIS',
       enable_pickup BOOLEAN DEFAULT TRUE,
       pickup_free BOOLEAN DEFAULT TRUE,
       is_active BOOLEAN DEFAULT TRUE,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

4. **Restart bot**
   ```bash
   systemctl restart parxpress-bot
   systemctl restart parxpress-web
   ```

5. **Test in admin panel**
   - Navigate to /delivery-settings
   - Verify settings load correctly
   - Try updating a value

### ✅ Testing Checklist

- [ ] Bot starts: `systemctl status parxpress-bot`
- [ ] Web app loads: `http://your-server:5000`
- [ ] Admin can login
- [ ] Delivery settings page accessible
- [ ] Can update threshold and cost
- [ ] In bot: checkout flow shows pickup button
- [ ] Selecting pickup → cost = 0
- [ ] 3+ items → auto free shipping
- [ ] 2 items + delivery → shows 2€
- [ ] Admin changes apply after restart

### 🔍 Debugging Commands

**Check bot logs**
```bash
journalctl -u parxpress-bot -f
```

**Check web logs**
```bash
journalctl -u parxpress-web -f
```

**Test delivery settings in DB**
```sql
SELECT * FROM delivery_settings;
```

**Test order with pickup**
```sql
SELECT address_data, delivery_type FROM orders WHERE address_data LIKE '%AKROPOLIS%';
```

---

**Version**: 1.0  
**Last Updated**: 2024  
**Status**: Ready for Deployment ✅
