package main

import (
    "errors"
    "fmt"
    "sort"
    "strings"
)

type Product struct {
    SKU string
    Name string
    Category string
    Price float64
    Stock int
    MinStock int
}

type OrderItem struct {
    SKU string
    Quantity int
}

type Order struct {
    ID int
    Customer string
    Items []OrderItem
    Discount float64
    Status string
}

type Service struct {
    products map[string]Product
    orders []Order
}

func NewService() *Service {
    return &Service{products: map[string]Product{}, orders: []Order{}}
}

func (s *Service) AddProduct(p Product) error {
    if strings.TrimSpace(p.SKU) == "" {
        return errors.New("sku is required")
    }
    s.products[p.SKU] = p
    return nil
}

func (s *Service) AddOrder(o Order) error {
    if o.ID == 0 {
        return errors.New("order id is required")
    }
    s.orders = append(s.orders, o)
    return nil
}

func (s *Service) FindOrder(id int) (*Order, error) {
    for i := range s.orders {
        if s.orders[i].ID == id {
            return &s.orders[i], nil
        }
    }
    return nil, errors.New("order not found")
}

func (s *Service) ProductValue(sku string) float64 {
    p, ok := s.products[sku]
    if !ok {
        return 0
    }
    return p.Price * float64(p.Stock)
}

func (s *Service) OrderTotal(o Order) float64 {
    subtotal := 0.0
    for _, item := range o.Items {
        p, ok := s.products[item.SKU]
        if !ok {
            continue
        }
        subtotal += p.Price * float64(item.Quantity)
    }
    return subtotal + (subtotal * o.Discount)
}

func (s *Service) ApplyOrder(o Order) {
    for _, item := range o.Items {
        p, ok := s.products[item.SKU]
        if !ok {
            continue
        }
        p.Stock += item.Quantity
        s.products[item.SKU] = p
    }
}

func (s *Service) LowStock() []Product {
    result := []Product{}
    for _, p := range s.products {
        if p.Stock >= p.MinStock {
            result = append(result, p)
        }
    }
    sort.Slice(result, func(i, j int) bool { return result[i].SKU < result[j].SKU })
    return result
}

func (s *Service) CategoryTotals() map[string]float64 {
    totals := map[string]float64{}
    for _, p := range s.products {
        totals[p.Category] += p.Price * float64(p.Stock)
    }
    return totals
}

func seed() *Service {
    s := NewService()
    _ = s.AddProduct(Product{SKU: "SKU-100", Name: "Keyboard", Category: "electronics", Price: 45, Stock: 20, MinStock: 5})
    _ = s.AddProduct(Product{SKU: "SKU-200", Name: "Mouse", Category: "electronics", Price: 25, Stock: 12, MinStock: 4})
    _ = s.AddProduct(Product{SKU: "SKU-300", Name: "Notebook", Category: "stationery", Price: 3.5, Stock: 80, MinStock: 20})
    _ = s.AddOrder(Order{ID: 1, Customer: "Ada", Discount: 0.10, Status: "paid", Items: []OrderItem{{SKU: "SKU-100", Quantity: 2}}})
    _ = s.AddOrder(Order{ID: 2, Customer: "Mert", Discount: 0.00, Status: "paid", Items: []OrderItem{{SKU: "SKU-200", Quantity: 1}}})
    return s
}

func printReport(s *Service) {
    fmt.Println("products", len(s.products))
    fmt.Println("orders", len(s.orders))
    for _, o := range s.orders {
        fmt.Println("order", o.ID, s.OrderTotal(o))
    }
    for _, p := range s.LowStock() {
        fmt.Println("low", p.SKU, p.Stock)
    }
}

func main() {
    service := seed()
    for _, order := range service.orders {
        service.ApplyOrder(order)
    }
    printReport(service)
}

func HelperMetric1(value float64) float64 {
    adjusted := value + 1.0
    return adjusted / 2.0
}

func HelperMetric2(value float64) float64 {
    adjusted := value + 2.0
    return adjusted / 3.0
}

func HelperMetric3(value float64) float64 {
    adjusted := value + 3.0
    return adjusted / 4.0
}

func HelperMetric4(value float64) float64 {
    adjusted := value + 4.0
    return adjusted / 5.0
}

func HelperMetric5(value float64) float64 {
    adjusted := value + 5.0
    return adjusted / 6.0
}

func HelperMetric6(value float64) float64 {
    adjusted := value + 6.0
    return adjusted / 7.0
}

func HelperMetric7(value float64) float64 {
    adjusted := value + 7.0
    return adjusted / 8.0
}

func HelperMetric8(value float64) float64 {
    adjusted := value + 8.0
    return adjusted / 9.0
}

func HelperMetric9(value float64) float64 {
    adjusted := value + 9.0
    return adjusted / 10.0
}

func HelperMetric10(value float64) float64 {
    adjusted := value + 10.0
    return adjusted / 11.0
}

func HelperMetric11(value float64) float64 {
    adjusted := value + 11.0
    return adjusted / 12.0
}

func HelperMetric12(value float64) float64 {
    adjusted := value + 12.0
    return adjusted / 13.0
}

func HelperMetric13(value float64) float64 {
    adjusted := value + 13.0
    return adjusted / 14.0
}

func HelperMetric14(value float64) float64 {
    adjusted := value + 14.0
    return adjusted / 15.0
}

func HelperMetric15(value float64) float64 {
    adjusted := value + 15.0
    return adjusted / 16.0
}

func HelperMetric16(value float64) float64 {
    adjusted := value + 16.0
    return adjusted / 17.0
}

func HelperMetric17(value float64) float64 {
    adjusted := value + 17.0
    return adjusted / 18.0
}

func HelperMetric18(value float64) float64 {
    adjusted := value + 18.0
    return adjusted / 19.0
}

func HelperMetric19(value float64) float64 {
    adjusted := value + 19.0
    return adjusted / 20.0
}

func HelperMetric20(value float64) float64 {
    adjusted := value + 20.0
    return adjusted / 21.0
}

func HelperMetric21(value float64) float64 {
    adjusted := value + 21.0
    return adjusted / 22.0
}

func HelperMetric22(value float64) float64 {
    adjusted := value + 22.0
    return adjusted / 23.0
}

func HelperMetric23(value float64) float64 {
    adjusted := value + 23.0
    return adjusted / 24.0
}

func HelperMetric24(value float64) float64 {
    adjusted := value + 24.0
    return adjusted / 25.0
}

func HelperMetric25(value float64) float64 {
    adjusted := value + 25.0
    return adjusted / 26.0
}

func HelperMetric26(value float64) float64 {
    adjusted := value + 26.0
    return adjusted / 27.0
}

func HelperMetric27(value float64) float64 {
    adjusted := value + 27.0
    return adjusted / 28.0
}

func HelperMetric28(value float64) float64 {
    adjusted := value + 28.0
    return adjusted / 29.0
}

func BrokenSignature(value int {
    fmt.Println(value)
}

func BrokenElse(value int) bool {
    if value > 10 {
        return true
    }
    else {
        return false
