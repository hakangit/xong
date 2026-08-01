import Foundation
import dnssd

/// Looks up a DNS TXT record using the device's own resolver.
///
/// Deliberately not DNS-over-HTTPS: that would hand the user's employer domain
/// to a third-party resolver on every sign-in, and add a dependency on someone
/// else's uptime. dnssd is part of the system and honours whatever resolver the
/// network already uses.
enum DNSTextLookup {
    /// Returns the TXT strings for `name`, or an empty array if there are none.
    /// Never throws — discovery treats "no record" and "lookup failed" the same
    /// way, by moving on to the next probe.
    static func txt(_ name: String, timeout: TimeInterval = 3) async -> [String] {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                continuation.resume(returning: query(name, timeout: timeout))
            }
        }
    }

    private final class Collector {
        var records: [String] = []
        /// The resolver answered "no such record". Without this the lookup
        /// would burn the whole timeout on every domain that has not published
        /// one — which is most of them, on the critical path of every sign-in.
        var resolved = false
    }

    private static func query(_ name: String, timeout: TimeInterval) -> [String] {
        var serviceRef: DNSServiceRef?
        let collector = Collector()

        let callback: DNSServiceQueryRecordReply = {
            _, _, _, errorCode, _, _, _, rdlen, rdata, _, context in
            guard let context else { return }
            let collector = Unmanaged<Collector>.fromOpaque(context).takeUnretainedValue()

            guard errorCode == kDNSServiceErr_NoError else {
                collector.resolved = true
                return
            }
            guard let rdata, rdlen > 0 else {
                collector.resolved = true
                return
            }
            let bytes = UnsafeRawBufferPointer(start: rdata, count: Int(rdlen))

            // TXT rdata is a sequence of length-prefixed strings, and a single
            // record may be split into several when it exceeds 255 bytes.
            var index = 0
            var assembled = ""
            while index < bytes.count {
                let length = Int(bytes[index])
                index += 1
                guard length > 0, index + length <= bytes.count else { break }
                let slice = bytes[index..<(index + length)]
                assembled += String(decoding: slice, as: UTF8.self)
                index += length
            }
            if !assembled.isEmpty { collector.records.append(assembled) }
        }

        let context = Unmanaged.passUnretained(collector).toOpaque()
        let status = DNSServiceQueryRecord(
            &serviceRef,
            kDNSServiceFlagsTimeout,
            0,
            name,
            UInt16(kDNSServiceType_TXT),
            UInt16(kDNSServiceClass_IN),
            callback,
            context
        )
        guard status == kDNSServiceErr_NoError, let serviceRef else { return [] }
        defer { DNSServiceRefDeallocate(serviceRef) }

        let socket = DNSServiceRefSockFD(serviceRef)
        guard socket >= 0 else { return [] }

        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            var readSet = fd_set()
            fdZero(&readSet)
            fdSet(socket, &readSet)

            var remaining = timeval(
                tv_sec: Int(max(0, deadline.timeIntervalSinceNow)),
                tv_usec: 0
            )
            let ready = select(socket + 1, &readSet, nil, nil, &remaining)
            if ready <= 0 { break }

            if DNSServiceProcessResult(serviceRef) != kDNSServiceErr_NoError { break }
            // One answer is enough; a domain should not publish two. `resolved`
            // covers the negative answer, so a missing record returns at once.
            if !collector.records.isEmpty || collector.resolved { break }
        }
        return collector.records
    }
}

// fd_set is an opaque tuple in Swift, so the C macros need reimplementing.
private func fdZero(_ set: inout fd_set) {
    set.fds_bits = (
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    )
}

private func fdSet(_ fd: Int32, _ set: inout fd_set) {
    let index = Int(fd) / 32
    let bit = Int32(1) << (Int32(fd) % 32)
    withUnsafeMutablePointer(to: &set.fds_bits) { pointer in
        pointer.withMemoryRebound(to: Int32.self, capacity: 32) { bits in
            bits[index] |= bit
        }
    }
}
