-- Create databases
CREATE DATABASE hotel_auth_db;
CREATE DATABASE hotel_booking_db;

-- Connect to hotel_booking_db and create tables
\c hotel_booking_db;

-- Main booking information
CREATE TABLE booking_info (
    booking_id BIGSERIAL PRIMARY KEY,
    
    -- Hotel and guest details
    hotel_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50), -- Changed from BIGINT to VARCHAR for username
    
    -- Stay details
    checkin_date DATE NOT NULL,
    checkout_date DATE NOT NULL,
    total_nights INTEGER NOT NULL CHECK (total_nights > 0),
    total_rooms INTEGER NOT NULL CHECK (total_rooms > 0),
    total_guests INTEGER NOT NULL CHECK (total_guests > 0),
    
    -- Pricing
    total_amount DECIMAL(10,2) NOT NULL CHECK (total_amount > 0),
    currency VARCHAR(3) DEFAULT 'INR',
    
    -- Status
    booking_status VARCHAR(20) DEFAULT 'CONFIRMED' CHECK (booking_status IN ('CONFIRMED', 'CANCELLED', 'FAILED')),
    payment_status VARCHAR(20) DEFAULT 'PENDING' CHECK (payment_status IN ('PENDING', 'PAID', 'FAILED', 'REFUNDED')),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT valid_dates CHECK (checkout_date > checkin_date)
);


-- Booked rooms tracking
CREATE TABLE booked_rooms (
    booked_room_id BIGSERIAL PRIMARY KEY,
    hotel_id VARCHAR(50) NOT NULL,
    room_type_code VARCHAR(50) NOT NULL,
    booking_date DATE NOT NULL,
    
    -- Booking details for this specific date
    rooms_booked INTEGER NOT NULL CHECK (rooms_booked > 0),
    cost_per_room_per_night DECIMAL(10,2) NOT NULL CHECK (cost_per_room_per_night > 0),
    
    -- Reference to main booking
    booking_id BIGINT NOT NULL,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(hotel_id, room_type_code, booking_date, booking_id)
);
-- Create indexes for better query performance
CREATE INDEX idx_booking_info_user_id ON booking_info(user_id);
CREATE INDEX idx_booked_rooms_hotel_date ON booked_rooms(hotel_id, booking_date);
CREATE INDEX idx_booked_rooms_booking_id ON booked_rooms(booking_id);
CREATE INDEX idx_booking_info_status ON booking_info(booking_status);
CREATE INDEX idx_booking_info_hotel ON booking_info(hotel_id);

-- Complete booking information (all booking data + additional details)
CREATE TABLE booking_details (
    booking_detail_id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL REFERENCES booking_info(booking_id) ON DELETE CASCADE,
    
    -- All booking info duplicated for complete record
    user_id VARCHAR(50), -- Changed from BIGINT to VARCHAR for username
    hotel_id VARCHAR(50) NOT NULL,
    checkin_date DATE NOT NULL,
    checkout_date DATE NOT NULL,
    total_guests INTEGER NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR',
    booking_status VARCHAR(20) NOT NULL,
    
    -- Contact info
    guest_name VARCHAR(100) NOT NULL,
    guest_email VARCHAR(100) NOT NULL,
    guest_phone VARCHAR(20),
    special_requests TEXT,
    
    -- Additional details
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    invoice_details JSONB DEFAULT '{}',
    payment_status VARCHAR(20) DEFAULT 'PENDING' CHECK (payment_status IN ('PENDING', 'PAID', 'FAILED', 'REFUNDED')),
    payment_method VARCHAR(30),
    payment_reference VARCHAR(100),
    
    -- Cancellation policy
    cancellation_policy_type VARCHAR(20) CHECK (cancellation_policy_type IN ('FREE', 'PARTIAL_REFUND', 'NON_REFUNDABLE')),
    free_cancellation_hours INTEGER,
    cancellation_fee_percentage DECIMAL(5,2),
    cancellation_deadline TIMESTAMP,
    refund_policy TEXT,
    
    -- Processing info
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_booking_details_booking_id ON booking_details(booking_id);
CREATE INDEX idx_booking_details_invoice ON booking_details(invoice_number);
