import { Alert, Input } from 'antd'
import Modal from 'antd/lib/modal/Modal'
import { useActions } from 'kea'
import React, { Dispatch, SetStateAction, useCallback, useRef, useState } from 'react'
import { organizationLogic } from 'scenes/organizationLogic'

export function CreateOrganizationModal({
    isVisible,
    setIsVisible,
}: {
    isVisible: boolean
    setIsVisible: Dispatch<SetStateAction<boolean>>
}): JSX.Element {
    const { createOrganization } = useActions(organizationLogic)
    const [errorMessage, setErrorMessage] = useState<string | null>(null)
    const inputRef = useRef<Input | null>(null)

    const closeModal: () => void = useCallback(() => {
        setErrorMessage(null)
        setIsVisible(false)
        if (inputRef.current) inputRef.current.setValue('')
    }, [inputRef, setIsVisible])

    return (
        <Modal
            title="Creating an Organization"
            okText="Create Organization"
            cancelText="Cancel"
            onOk={() => {
                const name = inputRef.current?.state.value?.trim()
                if (name) {
                    setErrorMessage(null)
                    createOrganization(name)
                    closeModal()
                } else {
                    setErrorMessage('Your organization needs a name!')
                }
            }}
            onCancel={closeModal}
            visible={isVisible}
        >
            <p>Organizations gather people building products together.</p>
            <Input
                addonBefore="Name"
                ref={inputRef}
                placeholder='for example "Acme Corporation"'
                maxLength={64}
                autoFocus
            />
            {errorMessage && <Alert message={errorMessage} type="error" style={{ marginTop: '1rem' }} />}
        </Modal>
    )
}
