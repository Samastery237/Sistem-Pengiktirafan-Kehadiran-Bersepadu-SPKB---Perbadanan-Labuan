const { formatIC, formatPhone } = require('./js/form.js');

describe('form.js Input Formatters', () => {
    
  describe('formatIC', () => {
    it('should format a valid 12 digit IC correctly', () => {
      expect(formatIC('900101123456')).toBe('900101-12-3456');
    });

    it('should handle partial inputs gracefully', () => {
      expect(formatIC('900101')).toBe('900101');
      expect(formatIC('90010112')).toBe('900101-12');
    });

    it('should strip non-numeric characters', () => {
      expect(formatIC('900101-12-3456abc')).toBe('900101-12-3456');
    });
  });

  describe('formatPhone', () => {
    it('should strip alphabetic characters', () => {
      expect(formatPhone('012abc3456789')).toBe('0123456789');
    });

    it('should allow +, -, and spaces', () => {
      expect(formatPhone('+60 12-345 6789')).toBe('+60 12-345 6789');
    });

    it('should truncate to 15 characters', () => {
      expect(formatPhone('12345678901234567890')).toBe('123456789012345');
    });
  });
});
