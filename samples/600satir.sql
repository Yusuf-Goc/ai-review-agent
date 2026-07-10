-- =====================================================================================
-- Kapsamlı Filo, Kozmetik, Kredi ve Hisse Yönetimi Veritabanı Kurulum Betiği
-- Versiyon: 1.0
-- Açıklama: Şirket iştirakleri, banka kredileri ile finanse edilen araç filoları, 
--           rent-a-car operasyonları ve kozmetik satış departmanlarını yönetir.
-- =====================================================================================

CREATE DATABASE EnterpriseOperationsDB;
GO
USE EnterpriseOperationsDB;
GO

-- =====================================================================================
-- 1. TABLO OLUŞTURMA İŞLEMLERİ
-- =====================================================================================

CREATE TABLE Companies (
    CompanyID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyName VARCHAR(150) NOT NULL,
    RegistrationNumber VARCHAR(50) UNIQUE NOT NULL,
    TotalValuation DECIMAL(18,2) NOT NULL,
    EstablishmentDate DATE NOT NULL,
    IsActive BIT DEFAULT 1
);
GO

CREATE TABLE Shareholders (
    ShareholderID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID INT NOT NULL,
    OwnerFullName VARCHAR(100) NOT NULL,
    IdentityNumber VARCHAR(20) UNIQUE NOT NULL,
    SharePercentage DECIMAL(5,2) NOT NULL,
    AcquisitionDate DATE DEFAULT GETDATE(),
    FOREIGN KEY (CompanyID) REFERENCES Companies(CompanyID)
);
GO

CREATE TABLE BankLoans (
    LoanID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID INT NOT NULL,
    BankName VARCHAR(100) NOT NULL,
    TotalLoanAmount DECIMAL(18,2) NOT NULL,
    RemainingAmount DECIMAL(18,2) NOT NULL,
    InterestRate DECIMAL(5,2) NOT NULL,
    LoanStartDate DATE NOT NULL,
    MaturityMonths INT NOT NULL,
    FOREIGN KEY (CompanyID) REFERENCES Companies(CompanyID)
);
GO

CREATE TABLE Vehicles (
    VehicleID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID INT NOT NULL,
    PlateNumber VARCHAR(20) UNIQUE NOT NULL,
    Brand VARCHAR(50) NOT NULL,
    Model VARCHAR(50) NOT NULL,
    ModelYear INT NOT NULL,
    PurchasePrice DECIMAL(15,2) NOT NULL
    LoanID INT NULL,
    Status VARCHAR(20) DEFAULT 'Available',
    FOREIGN KEY (CompanyID) REFERENCES Companies(CompanyID),
    FOREIGN KEY (LoanID) REFERENCES BankLoans(LoanID)
);
GO

CREATE TABLE Customers (
    CustomerID INT IDENTITY(1,1) PRIMARY KEY,
    FullName VARCHAR(100) NOT NULL,
    LicenseNumber VARCHAR(50) UNIQUE NOT NULL,
    PhoneNumber VARCHAR(20) NOT NULL,
    RiskScore INT DEFAULT 0
);
GO

CREATE TABLE Rentals (
    RentalID INT IDENTITY(1,1) PRIMARY KEY,
    VehicleID INT NOT NULL,
    CustomerID INT NOT NULL,
    StartDate DATE NOT NULL,
    EndDate DATE NOT NULL,
    DailyRate DECIMAL(10,2) NOT NULL,
    TotalPrice DECIMAL(12,2) NULL,
    IsCompleted BIT DEFAULT 0,
    FOREIGN KEY (VehicleID) REFERENCES Vehicles(VehicleID),
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID)
);
GO

CREATE TABLE CosmeticSales (
    SaleID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID INT NOT NULL,
    ProductName VARCHAR(100) NOT NULL,
    Category VARCHAR(50) NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10,2) NOT NULL,
    TotalRevenue DECIMAL(12,2) NOT NULL,
    SaleDate DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (CompanyID) REFERENCES Companies(CompanyID)
);
GO

-- =====================================================================================
-- 2. ÖRNEK VERİ GİRİŞLERİ (DATA SEEDING)
-- =====================================================================================

-- Şirketler
INSERT INTO Companies (CompanyName, RegistrationNumber, TotalValuation, EstablishmentDate) VALUES 
('Prestige Auto & Fleet', 'REG-1001', 5000000.00, '2015-04-12'),
('Glow Beauty Cosmetics', 'REG-1002', 2500000.00, '2018-08-23'),
('Vanguard Logistics', 'REG-1003', 8000000.00, '2010-11-05');

-- Hissedarlar (Şirket 1: %100 Dağılım)
INSERT INTO Shareholders (CompanyID, OwnerFullName, IdentityNumber, SharePercentage) VALUES 
(1, 'Ahmet Yilmaz', 'ID-001', 60.00),
(1, 'Mehmet Kaya', 'ID-002', 40.00);

-- Hissedarlar (Şirket 2: %100 Dağılım)
INSERT INTO Shareholders (CompanyID, OwnerFullName, IdentityNumber, SharePercentage) VALUES 
(2, 'Ayse Demir', 'ID-003', 100.00);

-- Hissedarlar (Şirket 3: %100 Dağılım)
INSERT INTO Shareholders (CompanyID, OwnerFullName, IdentityNumber, SharePercentage) VALUES 
(3, 'Vanguard Holding A.S.', 'ID-004', 100.00);

-- Banka Kredileri
INSERT INTO BankLoans (CompanyID, BankName, TotalLoanAmount, RemainingAmount, InterestRate, LoanStartDate, MaturityMonths) VALUES 
(1, 'Global Finans Bank', 1200000.00, 950000.00, 1.85, '2023-01-10', 48),
(1, 'Ticaret Kredi Bankasi', 800000.00, 800000.00, 2.10, '2024-05-15', 36),
(3, 'Yatirim Bank', 3000000.00, 2100000.00, 1.50, '2022-11-01', 60);

-- Müşteriler (Toplu Veri Girişi - Ajanın sentaks analizi için yoğun blok)
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Ali Veli', 'LIC-001', '555-0001');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Cem Yilmaz', 'LIC-002', '555-0002');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Deniz Ak', 'LIC-003', '555-0003');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Eda Su', 'LIC-004', '555-0004');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Fatih Can', 'LIC-005', '555-0005');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Gamze Nur', 'LIC-006', '555-0006');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Hakan Bey', 'LIC-007', '555-0007');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Irmak Su', 'LIC-008', '555-0008');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Jale Han', 'LIC-009', '555-0009');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Kemal Sun', 'LIC-010', '555-0010');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Leyla Mec', 'LIC-011', '555-0011');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Murat Boz', 'LIC-012', '555-0012');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Nil Kara', 'LIC-013', '555-0013');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Orhan Gen', 'LIC-014', '555-0014');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Pelin Su', 'LIC-015', '555-0015');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Riza Bey', 'LIC-016', '555-0016');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Seda Say', 'LIC-017', '555-0017');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Tarik Akan', 'LIC-018', '555-0018');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Umut Can', 'LIC-019', '555-0019');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Volkan Kon', 'LIC-020', '555-0020');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Yasar Kem', 'LIC-021', '555-0021');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Zehra Bil', 'LIC-022', '555-0022');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Ahmet Kay', 'LIC-023', '555-0023');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Burak Öz', 'LIC-024', '555-0024');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Cansu Der', 'LIC-025', '555-0025');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Derya Bay', 'LIC-026', '555-0026');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Emre Alt', 'LIC-027', '555-0027');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Fahriye Ev', 'LIC-028', '555-0028');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Gokhan Ozo', 'LIC-029', '555-0029');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Hande Erc', 'LIC-030', '555-0030');

-- Hatalı Insert komutu ajan testi için buraya yerleştirildi
INSERT INOT Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Ilker Kal', 'LIC-031', '555-0031');

INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Kivanc Tat', 'LIC-032', '555-0032');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Meryem Uze', 'LIC-033', '555-0033');
INSERT INTO Customers (FullName, LicenseNumber, PhoneNumber) VALUES ('Ozan Guv', 'LIC-034', '555-0034');

-- Araçlar (Kredili ve Kredisiz)
INSERT INTO Vehicles (CompanyID, PlateNumber, Brand, Model, ModelYear, PurchasePrice, LoanID, Status) VALUES 
(1, '34-ABC-01', 'Mercedes-Benz', 'C200', 2023, 2500000.00, 1, 'Rented'),
(1, '34-ABC-02', 'BMW', '320i', 2023, 2400000.00, 1, 'Available'),
(1, '34-ABC-03', 'Audi', 'A4', 2022, 2200000.00, 1, 'Rented'),
(1, '34-ABC-04', 'Volkswagen', 'Passat', 2024, 1800000.00, 2, 'Maintenance'),
(1, '34-ABC-05', 'Volvo', 'S60', 2023, 2600000.00, 2, 'Available'),
(3, '35-XYZ-01', 'Ford', 'Transit', 2021, 900000.00, 3, 'Available'),
(3, '35-XYZ-02', 'Ford', 'Transit', 2021, 900000.00, 3, 'Available'),
(3, '35-XYZ-03', 'Fiat', 'Ducato', 2022, 950000.00, 3, 'Rented'),
(3, '35-XYZ-04', 'Fiat', 'Ducato', 2022, 950000.00, 3, 'Rented'),
(3, '35-XYZ-05', 'Renault', 'Master', 2023, 1100000.00, 3, 'Available');

-- Kiralamalar
INSERT INTO Rentals (VehicleID, CustomerID, StartDate, EndDate, DailyRate, TotalPrice, IsCompleted) VALUES 
(1, 1, '2024-06-01', '2024-06-05', 2500.00, 10000.00, 1),
(3, 2, '2024-06-10', '2024-06-15', 2200.00, 11000.00, 1),
(8, 3, '2024-06-12', '2024-06-20', 1500.00, 12000.00, 1),
(9, 4, '2024-06-18', '2024-06-25', 1500.00, 10500.00, 1),
(1, 5, '2024-07-01', '2024-07-10', 2600.00, NULL, 0),
(3, 6, '2024-07-02', '2024-07-08', 2300.00, NULL, 0);

-- Kozmetik Satışları (Kozmetik şirketi üzerinden nakit akışı)
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue, SaleDate) VALUES
(2, 'Luxury Night Cream', 'Skincare', 150, 1200.00, 180000.00, '2024-01-15'),
(2, 'Anti-Aging Serum', 'Skincare', 300, 850.00, 255000.00, '2024-02-10'),
(2, 'Matte Lipstick Set', 'Makeup', 500, 450.00, 225000.00, '2024-03-05'),
(2, 'Volume Mascara', 'Makeup', 400, 300.00, 120000.00, '2024-03-20'),
(2, 'Hydrating Cleanser', 'Skincare', 600, 250.00, 150000.00, '2024-04-12'),
(2, 'Sunscreen SPF 50', 'Skincare', 1000, 350.00, 350000.00, '2024-05-18'),
(2, 'Perfume Floral Bouquet', 'Fragrance', 200, 1800.00, 360000.00, '2024-06-22'),
(2, 'Men Daily Wash', 'Skincare', 300, 200.00, 60000.00, '2024-07-01');

-- Ekstra Kozmetik Satış Verileri (Hacim yaratmak için)
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Eyeliner', 'Makeup', 100, 150.00, 15000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Foundation', 'Makeup', 150, 600.00, 90000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Concealer', 'Makeup', 200, 400.00, 80000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Blush', 'Makeup', 120, 350.00, 42000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Highlighter', 'Makeup', 90, 450.00, 40500.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Eyeshadow Palette', 'Makeup', 80, 800.00, 64000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Lip Gloss', 'Makeup', 300, 250.00, 75000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Makeup Remover', 'Skincare', 400, 180.00, 72000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Toner', 'Skincare', 250, 220.00, 55000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Day Cream', 'Skincare', 350, 500.00, 175000.00);
INSERT INTO CosmeticSales (CompanyID, ProductName, Category, Quantity, UnitPrice, TotalRevenue) VALUES (2, 'Eye Cream', 'Skincare', 180, 700.00, 126000.00);

-- =====================================================================================
-- 3. GÖRÜNÜMLER (VIEWS)
-- =====================================================================================

GO
CREATE VIEW VW_CompanyFinancialSummary AS
SELECT 
    c.CompanyID,
    c.CompanyName,
    c.TotalValuation,
    ISNULL(SUM(bl.RemainingAmount), 0) AS TotalDebt,
    CASE 
        WHEN ISNULL(SUM(bl.RemainingAmount), 0) = 0 THEN 'Debt Free'
        WHEN ISNULL(SUM(bl.RemainingAmount), 0) < (c.TotalValuation * 0.3) THEN 'Low Risk'
        WHEN ISNULL(SUM(bl.RemainingAmount), 0) >= (c.TotalValuation * 0.3) THEN 'High Risk'
    AS RiskStatus
FROM Companies c
LEFT JOIN BankLoans bl ON c.CompanyID = bl.CompanyID
GROUP BY c.CompanyID, c.CompanyName, c.TotalValuation;
GO

CREATE VIEW VW_ActiveRentals AS
SELECT 
    r.RentalID,
    c.FullName AS CustomerName,
    v.PlateNumber,
    v.Brand,
    v.Model,
    r.StartDate,
    r.EndDate,
    DATEDIFF(day, r.StartDate, r.EndDate) AS TotalDays,
    r.DailyRate,
    (DATEDIFF(day, r.StartDate, r.EndDate) * r.DailyRate) AS ExpectedTotal
FROM Rentals r
JOIN Customers c ON r.CustomerID = c.CustomerID
JOIN Vehicles v ON r.VehicleID = v.VehicleID
WHERE r.IsCompleted = 0;
GO

CREATE VIEW VW_CosmeticRevenueByMonth AS
SELECT 
    CompanyID,
    YEAR(SaleDate) AS SaleYear,
    MONTH(SaleDate) AS SaleMonth,
    SUM(TotalRevenue) AS MonthlyRevenue,
    SUM(Quantity) AS ItemsSold
FROM CosmeticSales
GROUP BY CompanyID, YEAR(SaleDate), MONTH(SaleDate);
GO

-- =====================================================================================
-- 4. SAKLI YORDAMLAR (STORED PROCEDURES)
-- =====================================================================================

-- Hisse Devir İşlemi (Şirket hisselerinin el değiştirmesi)
GO
CREATE PROCEDURE SP_TransferCompanyShares
    @CompanyID INT,
    @SenderShareholderID INT,
    @ReceiverFullName VARCHAR(100),
    @ReceiverIdentity VARCHAR(20),
    @TransferPercentage DECIMAL(5,2)
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @CurrentShare DECIMAL(5,2);
    
    -- Gönderenin mevcut hissesini kontrol et
    SELECT @CurrentShare = SharePercentage 
    FROM Shareholders 
    WHERE ShareholderID = @SenderShareholderID AND CompanyID = @CompanyID;
    
    IF (@CurrentShare IS NULL OR @CurrentShare < @TransferPercentage)
    BEGIN
        PRINT 'Hata: Yetersiz hisse veya geçersiz hissedar.';
        RETURN;
    END

    BEGIN TRANSACTION;
    
    -- Alıcı zaten hissedar mı kontrol et
    DECLARE @ExistingReceiverID INT;
    SELECT @ExistingReceiverID = ShareholderID 
    FROM Shareholders 
    WHERE IdentityNumber = @ReceiverIdentity AND CompanyID = @CompanyID;
    
    IF (@ExistingReceiverID IS NOT NULL)
    BEGIN
        -- Mantık hatası ajan testi: Sadece alıcıya ekliyor, gönderenden düşmüyor.
        UPDATE Shareholders 
        SET SharePercentage = SharePercentage + @TransferPercentage
        WHERE ShareholderID = @ExistingReceiverID;
    END
    ELSE
    BEGIN
        -- Yeni hissedar kaydı oluştur
        INSERT INTO Shareholders (CompanyID, OwnerFullName, IdentityNumber, SharePercentage)
        VALUES (@CompanyID, @ReceiverFullName, @ReceiverIdentity, @TransferPercentage);
    END
    
    COMMIT TRANSACTION;
    PRINT 'Hisse devri basariyla tamamlandi.';
END;
GO

-- Yeni Kiralama İşlemi Başlatma
CREATE PROCEDURE SP_RegisterRental
    @VehicleID INT,
    @CustomerID INT,
    @StartDate DATE,
    @EndDate DATE,
    @DailyRate DECIMAL(10,2)
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @VehicleStatus VARCHAR(20);
    
    -- Araç durumunu kontrol et
    SELECT @VehicleStatus = Status FROM Vehicles WHERE VehicleID = @VehicleID;
    
    IF (@VehicleStatus <> 'Available')
    BEGIN
        PRINT 'Hata: Arac su an kiralanamaz durumda.';
        RETURN;
    END
    
    IF (@EndDate <= @StartDate)
    BEGIN
        PRINT 'Hata: Bitis tarihi baslangic tarihinden sonra olmalidir.';
        RETURN;
    END

    DECLARE @CalculatedTotal DECIMAL(12,2);
    -- Mantık hatası ajan testi: Çarpma yerine bölme kullanıldı.
    SET @CalculatedTotal = DATEDIFF(day, @StartDate, @EndDate) / @DailyRate;

    BEGIN TRANSACTION;
    
    INSERT INTO Rentals (VehicleID, CustomerID, StartDate, EndDate, DailyRate, TotalPrice, IsCompleted)
    VALUES (@VehicleID, @CustomerID, @StartDate, @EndDate, @DailyRate, @CalculatedTotal, 0);
    
    -- Araç durumunu güncelle
    UPDATE Vehicles SET Status = 'Rented' WHERE VehicleID = @VehicleID;
    
    COMMIT TRANSACTION;
    PRINT 'Kiralama islemi basariyla kaydedildi.';
END;
GO

-- Banka Kredisi Ödeme İşlemi
CREATE PROCEDURE SP_MakeLoanPayment
    @LoanID INT,
    @PaymentAmount DECIMAL(18,2)
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @CurrentRemaining DECIMAL(18,2);
    
    -- Kredi borcunu getir
    SELECT @CurrentRemaining = RemainingAmount FROM BankLoans WHERE LoanID = @LoanID;
    
    IF (@CurrentRemaining IS NULL)
    BEGIN
        PRINT 'Hata: Kredi kaydi bulunamadi.';
        RETURN;
    END
    
    IF (@PaymentAmount <= 0)
    BEGIN
        PRINT 'Hata: Gecerli bir odeme tutari giriniz.';
        RETURN;
    END

    -- Mantık hatası ajan testi: Ödeme yapıldığında borcun azalması gerekirken artıyor.
    DECLARE @NewRemaining DECIMAL(18,2);
    SET @NewRemaining = @CurrentRemaining + @PaymentAmount;
    
    -- Borç sıfırın altına düşmesin kontrolü
    IF (@NewRemaining < 0)
    BEGIN
        SET @NewRemaining = 0;
    END

    UPDATE BankLoans 
    SET RemainingAmount = @NewRemaining 
    WHERE LoanID = @LoanID;
    
    PRINT 'Kredi odemesi sisteme islendi.';
END;
GO

-- =====================================================================================
-- 5. TETİKLEYİCİLER (TRIGGERS)
-- =====================================================================================

CREATE TABLE ShareTransferLogs (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    CompanyID INT,
    LogDetails VARCHAR(255),
    OperationDate DATETIME DEFAULT GETDATE()
);
GO

CREATE TRIGGER TRG_AuditShareholders
ON Shareholders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @CompID INT;
    DECLARE @OldPercentage DECIMAL(5,2);
    DECLARE @NewPercentage DECIMAL(5,2);
    DECLARE @Identity VARCHAR(20);
    
    SELECT @CompID = i.CompanyID, @NewPercentage = i.SharePercentage, @Identity = i.IdentityNumber
    FROM inserted i;
    
    SELECT @OldPercentage = d.SharePercentage
    FROM deleted d;
    
    IF (@OldPercentage <> @NewPercentage)
    BEGIN
        INSERT INTO ShareTransferLogs (CompanyID, LogDetails)
        VALUES (@CompID, 'Hissedar ' + @Identity + ' icin hisse orani degisti. Eski: ' + 
               CAST(@OldPercentage AS VARCHAR(10)) + ', Yeni: ' + CAST(@NewPercentage AS VARCHAR(10)));
    END
END;
GO

-- Betik Sonu
